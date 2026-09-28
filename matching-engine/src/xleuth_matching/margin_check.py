"""Margin / risk pre-check before an order enters the book.

Every order must clear validation against live on-chain state (via web3.py)
before it is accepted:

  1. static rules: basket known + tradeable, price in (0, scale] and on the
     configured tick, size >= MIN_ORDER_SIZE, leverage in [1, MAX_LEVERAGE]
  2. oracle freshness: the IndexOracleConsumer price for the basket must
     exist and be newer than ORACLE_MAX_PRICE_STALENESS_SECONDS — the
     PositionManager requires the same at execution, so we reject early
     with a specific reason instead of failing at fill time
  3. margin: required margin = (oracle_price * size) / leverage must be
     covered by the user's free balance in the CollateralVault. Margin uses
     the on-chain oracle price (0-100 integer scale) because that is exactly
     what PositionManager.updatePosition locks at execution; the fill price
     is execution-only in v1.

Rejection reasons are specific and code-path-identifiable so the API and the
Week-5 verification can show why an order was refused.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

from xleuth_matching.config import MatchingConfig
from xleuth_matching.orderbook import Side
from xleuth_shared.basket_lifecycle import is_tradeable

logger = logging.getLogger("xleuth_matching.margin_check")


@dataclass
class CheckResult:
    ok: bool
    reason: str | None = None
    details: dict = field(default_factory=dict)

    @property
    def message(self) -> str:
        if self.ok:
            return "ok"
        suffix = f" ({self.details})" if self.details else ""
        return f"{self.reason}{suffix}"


class ChainState(ABC):
    """Reads the on-chain state the engine needs. Web3ChainState hits Amoy;
    tests use a fake."""

    @abstractmethod
    def oracle_price(self, basket_name: str) -> tuple[int, int] | None:
        """(price, updated_at_unix) of the latest accepted oracle update, or None."""

    @abstractmethod
    def free_balance(self, wallet: str) -> int:
        """User's free (unlocked) USDC balance in the CollateralVault (6-dp units)."""

    @abstractmethod
    def max_leverage(self) -> int:
        """Current PositionManager.maxLeverage."""

    @abstractmethod
    def position_size(self, wallet: str, basket_name: str) -> int:
        """Current on-chain position size of the user on the basket (0 if none)."""

    @abstractmethod
    def get_position(self, wallet: str, basket_name: str) -> tuple[int, int, int] | None:
        """Get full position details: (side, size, leverage). Side: 0=Long(BUY), 1=Short(SELL).
        Returns None if no position exists."""


class Web3ChainState(ChainState):
    """web3.py reads against the deployed vault / PositionManager / oracle."""

    ORACLE_ABI = [
        {
            "inputs": [{"internalType": "bytes32", "name": "basketId", "type": "bytes32"}],
            "name": "latestPrice",
            "outputs": [
                {"internalType": "uint256", "name": "price", "type": "uint256"},
                {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
            ],
            "stateMutability": "view",
            "type": "function",
        }
    ]
    VAULT_ABI = [
        {
            "inputs": [{"internalType": "address", "name": "user", "type": "address"}],
            "name": "freeBalance",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function",
        }
    ]
    PM_ABI = [
        {
            "inputs": [],
            "name": "maxLeverage",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [
                {"internalType": "address", "name": "user", "type": "address"},
                {"internalType": "bytes32", "name": "basketId", "type": "bytes32"},
            ],
            "name": "getPosition",
            "outputs": [
                {"internalType": "enum PositionManager.Side", "name": "side", "type": "uint8"},
                {"internalType": "uint256", "name": "size", "type": "uint256"},
                {"internalType": "uint256", "name": "entryPrice", "type": "uint256"},
                {"internalType": "uint256", "name": "leverage", "type": "uint256"},
                {"internalType": "uint256", "name": "lockedMargin", "type": "uint256"},
            ],
            "stateMutability": "view",
            "stateMutability": "view",
            "type": "function",
        },
    ]

    def __init__(self, config: MatchingConfig):
        from web3 import Web3

        self._w3 = Web3(Web3.HTTPProvider(config.rpc_url, request_kwargs={"timeout": 15}))
        self._checksum = Web3.to_checksum_address
        self._oracle = self._w3.eth.contract(
            address=config.oracle_consumer_address, abi=self.ORACLE_ABI
        )
        self._vault = self._w3.eth.contract(address=config.vault_address, abi=self.VAULT_ABI)
        self._pm = self._w3.eth.contract(
            address=config.position_manager_address, abi=self.PM_ABI
        )

    @staticmethod
    def basket_id(basket_name: str) -> bytes:
        from eth_utils import keccak

        return keccak(text=basket_name)

    def oracle_price(self, basket_name: str) -> tuple[int, int] | None:
        try:
            price, ts = self._oracle.functions.latestPrice(self.basket_id(basket_name)).call()
            return int(price), int(ts)
        except Exception:
            logger.warning("oracle latestPrice read failed for %s", basket_name, exc_info=True)
            return None

    def free_balance(self, wallet: str) -> int:
        try:
            return int(self._vault.functions.freeBalance(self._checksum(wallet)).call())
        except Exception:
            logger.warning("freeBalance read failed for %s", wallet, exc_info=True)
            return 0

    def max_leverage(self) -> int:
        try:
            return int(self._pm.functions.maxLeverage().call())
        except Exception:
            logger.warning("maxLeverage read failed", exc_info=True)
            return 0

    def position_size(self, wallet: str, basket_name: str) -> int:
        try:
            result = self._pm.functions.getPosition(
                self._checksum(wallet), self.basket_id(basket_name)
            ).call()
            return int(result[1])
        except Exception:
            logger.warning("getPosition read failed for %s/%s", wallet, basket_name, exc_info=True)
            return 0

    def get_position(self, wallet: str, basket_name: str) -> tuple[int, int, int] | None:
        """Get full position details: (side, size, leverage).
        Side: 0=Long(BUY), 1=Short(SELL). Returns None if no position or error."""
        try:
            result = self._pm.functions.getPosition(
                self._checksum(wallet), self.basket_id(basket_name)
            ).call()
            side = int(result[0])
            size = int(result[1])
            leverage = int(result[3])
            if size == 0:
                return None
            return (side, size, leverage)
        except Exception:
            logger.warning("getPosition read failed for %s/%s", wallet, basket_name, exc_info=True)
            return None


@dataclass
class MarginCheck:
    config: MatchingConfig
    chain: ChainState

    def validate(
        self,
        basket_name: str,
        wallet: str,
        side: Side,
        price: float | None,  # None for market orders
        size: float,
        leverage: int,
    ) -> CheckResult:
        checks = [
            self._check_basket(basket_name),
            self._check_size(size),
            self._check_leverage(leverage),
        ]
        # Only validate price for limit orders
        if price is not None:
            checks.append(self._check_price(price))
        for check in checks:
            if not check.ok:
                return check

        oracle = self.chain.oracle_price(basket_name)
        now = int(datetime.now(timezone.utc).timestamp())
        if oracle is None:
            return CheckResult(False, "oracle_unreadable", {"basket_name": basket_name})
        price_int, updated_at = oracle
        if price_int <= 0:
            return CheckResult(False, "oracle_price_zero", {"basket_name": basket_name})
        age = now - updated_at
        if updated_at == 0 or age > self.config.max_price_staleness_seconds:
            return CheckResult(
                False,
                "oracle_price_stale",
                {"age_seconds": age, "max_staleness_seconds": self.config.max_price_staleness_seconds},
            )

        max_lev = self.chain.max_leverage()
        if max_lev <= 0:
            return CheckResult(False, "leverage_cap_unreadable", {})
        if leverage > max_lev:
            return CheckResult(
                False, "leverage_above_cap", {"requested": leverage, "cap": max_lev}
            )

        required = (price_int * size) / leverage
        free = self.chain.free_balance(wallet) / 1e6
        if free + 1e-9 < required:
            return CheckResult(
                False,
                "insufficient_margin",
                {
                    "required_usdc": round(required, 2),
                    "free_usdc": round(free, 2),
                    "oracle_price": price_int,
                    "size": size,
                    "leverage": leverage,
                },
            )

        return CheckResult(True, details={"oracle_price": price_int, "required_usdc": round(required, 2)})

    # ── static checks ─────────────────────────────────────────────────────

    def _check_basket(self, basket_name: str) -> CheckResult:
        if basket_name not in self.config.baskets:
            return CheckResult(
                False, "unknown_basket", {"basket_name": basket_name, "known": self.config.baskets}
            )
        if not is_tradeable(basket_name):
            return CheckResult(False, "basket_not_tradeable", {"basket_name": basket_name})
        return CheckResult(True)

    def _check_price(self, price: float) -> CheckResult:
        if price <= 0 or price > self.config.price_scale:
            return CheckResult(
                False, "price_out_of_range", {"price": price, "scale": self.config.price_scale}
            )
        tick = self.config.tick_size
        if abs(round(price / tick) - price / tick) > 1e-6:
            return CheckResult(False, "price_not_on_tick", {"price": price, "tick": tick})
        return CheckResult(True)

    def _check_size(self, size: float) -> CheckResult:
        if size < self.config.min_order_size:
            return CheckResult(
                False, "size_below_min", {"size": size, "min": self.config.min_order_size}
            )
        return CheckResult(True)

    def _check_leverage(self, leverage: int) -> CheckResult:
        if leverage < 1 or leverage > self.config.max_leverage:
            return CheckResult(
                False, "leverage_out_of_range", {"leverage": leverage, "max": self.config.max_leverage}
            )
        return CheckResult(True)