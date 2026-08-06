"""On-chain settlement bridge for matched fills.

Week-5 spec (3): on a match, submit the resulting position
open/increase/close to PositionManager.updatePosition on-chain, and only
confirm the fill to the user once the transaction is mined.

Design:

* Fills are grouped per (trader, basket) and NETTED within a settlement
  batch: a trader whose fills include a 100 buy and a 40 sell on the same
  basket pays one transaction for the net +60 long instead of two. A net of
  zero (fills offset) needs no on-chain transaction at all.
* The bridge signs the PositionManager.updatePosition call with the
  trader's own key (from TRADER{1,2,...}_PRIVATE_KEY in the environment),
  so the transaction originates from the trader's EOA and the vault locks
  margin from exactly the account the engine pre-checked.
* Size is converted from engine floats to whole index units (the contract
  works in integer index units); a net that rounds to zero (dust) is
  skipped — no transaction is needed.
* Leverage of a netted update is the volume-weighted mean of the fills'
  leverages, rounded to a whole number (>= 1).
* Every submission is awaited to a mined receipt; status != 1 (revert) is
  surfaced as a settlement failure with the tx hash, and an alert is
  published to Redis (`xleuth:engine:alerts`) so the service can
  cancel/reject the affected orders loudly instead of silently confirming.

The bridge never raises for on-chain failures: it returns outcomes. Only
unknown trader keys (a config problem) produce an error outcome too, rather
than crashing the match loop.
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from xleuth_matching.config import MatchingConfig
from xleuth_matching.margin_check import Web3ChainState
from xleuth_matching.orderbook import Fill, Side

logger = logging.getLogger("xleuth_matching.settlement")

UPDATE_POSITION_ABI = [
    {
        "inputs": [
            {"internalType": "bytes32", "name": "basketId", "type": "bytes32"},
            {"internalType": "enum PositionManager.Side", "name": "side", "type": "uint8"},
            {"internalType": "uint256", "name": "size", "type": "uint256"},
            {"internalType": "uint256", "name": "leverage", "type": "uint256"},
        ],
        "name": "updatePosition",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]

SIDE_TO_ENUM = {Side.BUY: 0, Side.SELL: 1}  # PositionManager.Side: Long=0, Short=1

ALERT_CHANNEL = "xleuth:engine:alerts"
CONFIRM_TIMEOUT_SECONDS = 120


@dataclass
class PositionUpdate:
    """One net on-chain submission for a (trader, basket) fill group."""

    wallet: str
    basket_name: str
    side: Side
    size: float
    leverage: int

    @property
    def size_int(self) -> int:
        return int(round(self.size))


@dataclass
class SettlementOutcome:
    update: PositionUpdate
    ok: bool = False
    tx_hash: str | None = None
    error: str | None = None
    mined_at: str | None = None

    @property
    def reason(self) -> str:
        return self.error or ("mined" if self.ok else "not_mined")


class TxSubmitter(ABC):
    """Signs and submits a position update, waiting for the mined receipt."""

    @abstractmethod
    def submit(self, update: PositionUpdate) -> tuple[str, dict]:
        """Return (tx_hash, receipt) or raise with a revert/error message."""


class Web3TxSubmitter(TxSubmitter):
    def __init__(self, config: MatchingConfig, w3=None):
        from web3 import Web3

        self._w3 = w3 or Web3(Web3.HTTPProvider(config.rpc_url, request_kwargs={"timeout": 15}))
        self._pm = self._w3.eth.contract(
            address=config.position_manager_address, abi=UPDATE_POSITION_ABI
        )
        self._keys = {k.lower(): v for k, v in config.trader_keys.items()}
        self._chain_id = config.chain_id
        self._confirm_timeout = CONFIRM_TIMEOUT_SECONDS

    def submit(self, update: PositionUpdate) -> tuple[str, dict]:
        key = self._keys.get(update.wallet.lower())
        if key is None:
            raise ValueError(
                f"no private key configured for trader {update.wallet} "
                "(set TRADER{1,2,...}_PRIVATE_KEY matching the wallet)"
            )
        from eth_account import Account

        account = Account.from_key(key)

        basket_id = Web3ChainState.basket_id(update.basket_name)
        call = self._pm.functions.updatePosition(
            basket_id,
            SIDE_TO_ENUM[update.side],
            update.size_int,
            update.leverage,
        )

        base_fee = self._w3.eth.gas_price
        # Amoy enforces a minimum gas tip (currently 25 gwei); be generous.
        max_priority_fee = self._w3.to_wei(30, "gwei")

        def build(fee_factor: float) -> dict:
            return call.build_transaction(
                {
                    "from": account.address,
                    "nonce": self._w3.eth.get_transaction_count(account.address, "pending"),
                    "gas": 300_000,
                    "maxFeePerGas": int(base_fee * fee_factor) + max_priority_fee,
                    "maxPriorityFeePerGas": max_priority_fee,
                    "chainId": self._chain_id,
                }
            )

        def send(tx: dict) -> str:
            signed = account.sign_transaction(tx)
            return self._w3.eth.send_raw_transaction(signed.raw_transaction).hex()

        tx_hash = send(build(1.0))
        deadline = time.monotonic() + self._confirm_timeout
        fee_factor = 1.0
        bumps = 0
        while time.monotonic() < deadline:
            try:
                receipt = self._w3.eth.get_transaction_receipt(tx_hash)
            except Exception:
                receipt = None
            if receipt is not None:
                return tx_hash, receipt
            try:
                self._w3.eth.get_transaction(tx_hash)
                in_pool = True
            except Exception:
                in_pool = False
            if not in_pool and bumps < 3:
                # Dropped from the pool (e.g. base fee moved): rebroadcast
                # with a bumped fee on the same nonce.
                bumps += 1
                fee_factor *= 1.5
                logger.warning(
                    "tx %s left the pool; rebroadcasting (bump %d, fee x%.1f)",
                    tx_hash,
                    bumps,
                    fee_factor,
                )
                try:
                    tx_hash = send(build(fee_factor))
                except Exception as exc:
                    logger.warning("rebroadcast failed: %s", exc)
            time.sleep(2)
        raise TimeoutError(f"transaction {tx_hash} not mined within {self._confirm_timeout}s")


class SettlementBridge:
    """Groups fills into net position updates and settles them on-chain."""

    def __init__(self, config: MatchingConfig, submitter: TxSubmitter | None = None):
        self.config = config
        self._submitter = submitter or Web3TxSubmitter(config)
        self.redis = None
        if config.redis_url:
            try:
                import redis

                self.redis = redis.Redis.from_url(config.redis_url, decode_responses=True)
            except Exception:
                logger.warning("redis unavailable; alerts will only be logged", exc_info=True)

    def settle_fills(self, fills: list[Fill]) -> list[SettlementOutcome]:
        """Settle a batch of fills. Returns one outcome per on-chain submission.

        Groups that net to zero, or to dust after integer rounding, produce
        no submission (nothing needs to happen on-chain).
        """
        if not fills:
            return []
        outcomes: list[SettlementOutcome] = []
        for update in self._group(fills):
            try:
                tx_hash, receipt = self._submitter.submit(update)
                if receipt.get("status") != 1:
                    error = f"tx reverted on-chain: {tx_hash}"
                    logger.error(
                        "SETTLEMENT REVERT %s/%s tx=%s", update.wallet, update.basket_name, tx_hash
                    )
                    outcomes.append(SettlementOutcome(update=update, error=error, tx_hash=tx_hash))
                    self._alert(update, error)
                else:
                    logger.info(
                        "SETTLEMENT OK %s/%s size=%d side=%s lev=%d tx=%s",
                        update.wallet,
                        update.basket_name,
                        update.size_int,
                        update.side.value,
                        update.leverage,
                        tx_hash,
                    )
                    outcomes.append(
                        SettlementOutcome(
                            update=update,
                            ok=True,
                            tx_hash=tx_hash,
                            mined_at=datetime.now(timezone.utc).isoformat(),
                        )
                    )
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                logger.error("SETTLEMENT FAILED %s/%s: %s", update.wallet, update.basket_name, error)
                outcomes.append(SettlementOutcome(update=update, error=error))
                self._alert(update, error)
        return outcomes

    # ── grouping / netting ───────────────────────────────────────────────

    def _group(self, fills: list[Fill]) -> list[PositionUpdate]:
        """Net fill legs per (trader, basket) into one PositionUpdate each."""
        legs: dict[tuple[str, str], list[tuple[Side, float, int]]] = defaultdict(list)
        for fill in fills:
            for wallet, side, leverage in (
                (fill.taker_trader, fill.taker_side, fill.taker_leverage),
                (fill.maker_trader, fill.maker_side, fill.maker_leverage),
            ):
                key = wallet.lower()
                if key not in self.config.trader_keys:
                    logger.warning(
                        "fill %s references untracked trader %s; skipping leg",
                        fill.trade_id,
                        wallet,
                    )
                    continue
                legs[(key, fill.basket_name)].append((side, fill.size, leverage))

        updates: list[PositionUpdate] = []
        for (wallet, basket_name), group_legs in legs.items():
            net = sum(size if side is Side.BUY else -size for side, size, _ in group_legs)
            if abs(net) < 1e-9:
                logger.info("net-zero fills for %s/%s; no on-chain update", wallet, basket_name)
                continue
            side = Side.BUY if net > 0 else Side.SELL
            size = abs(net)
            if round(size) == 0:
                logger.info("dust net for %s/%s (%.4f); skipping", wallet, basket_name, size)
                continue
            total_size = sum(leg_size for _, leg_size, _ in group_legs)
            leverage = max(1, int(round(sum(lev * sz for _, sz, lev in group_legs) / total_size)))
            updates.append(
                PositionUpdate(wallet=wallet, basket_name=basket_name, side=side, size=size, leverage=leverage)
            )
        return updates

    # ── alerts ───────────────────────────────────────────────────────────

    def _alert(self, update: PositionUpdate, error: str) -> None:
        payload = json.dumps(
            {
                "event": "settlement_failed",
                "wallet": update.wallet,
                "basket_name": update.basket_name,
                "size": update.size,
                "side": update.side.value,
                "error": error,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        )
        logger.error("ENGINE ALERT settlement_failed %s", payload)
        if self.redis is not None:
            try:
                self.redis.publish(ALERT_CHANNEL, payload)
            except Exception:
                logger.warning("failed to publish alert to redis", exc_info=True)
