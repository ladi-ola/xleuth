"""V2 atomic relay transport; NOT wired to the legacy settlement bridge.

Only a relayer key signs the outer transaction. Trader signatures are opaque
wallet-produced bytes, verified by SignedOrderExecutor (including ERC-1271).
No independent per-trader transactions, netting, skipped legs or dust success.

Live integration remains blocked on the reviewed atomic financial ledger and
durable order/receipt reconciliation. This transport never enables old PM
execution as a fallback when the V2 ledger/address/configuration is missing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from threading import Lock
from typing import Protocol

from xleuth_shared.trade_authorization import (
    AUTHORIZATION_FIELDS,
    MAX_PRICE_UNITS,
    MIN_NOTIONAL_UNITS,
    TradeAuthorization,
    notional_units,
)

_AUTH_TUPLE = {"name": "buy", "type": "tuple", "components": AUTHORIZATION_FIELDS}
EXECUTOR_ABI = [{
    "name": "executeMatches", "type": "function", "stateMutability": "nonpayable",
    "inputs": [{"name": "matches", "type": "tuple[]", "components": [
        _AUTH_TUPLE,
        {"name": "buySignature", "type": "bytes"},
        {**_AUTH_TUPLE, "name": "sell"},
        {"name": "sellSignature", "type": "bytes"},
        {"name": "size", "type": "uint256"},
        {"name": "price", "type": "uint256"},
        {"name": "buyIntent", "type": "bytes"},
        {"name": "sellIntent", "type": "bytes"},
    ]}],
    "outputs": [],
}, {
    "name": "MatchExecuted", "type": "event", "anonymous": False,
    "inputs": [
        {"name": "buyDigest", "type": "bytes32", "indexed": True},
        {"name": "sellDigest", "type": "bytes32", "indexed": True},
        {"name": "basketId", "type": "bytes32", "indexed": True},
        {"name": "size", "type": "uint256", "indexed": False},
        {"name": "price", "type": "uint256", "indexed": False},
        {"name": "notional", "type": "uint256", "indexed": False},
    ],
}]


@dataclass(frozen=True)
class AuthorizedMatch:
    buy: TradeAuthorization
    buy_signature: bytes
    sell: TradeAuthorization
    sell_signature: bytes
    size: int
    price: int
    buy_intent: bytes
    sell_intent: bytes

    def __post_init__(self) -> None:
        from eth_utils import keccak

        if self.buy.side != 0 or self.sell.side != 1:
            raise ValueError("a match requires one buy and one sell")
        if self.buy.trader.lower() == self.sell.trader.lower():
            raise ValueError("self-trade is not allowed")
        if self.buy.basket_id.lower() != self.sell.basket_id.lower():
            raise ValueError("basket identifiers differ")
        if self.buy.order_id.lower() == self.sell.order_id.lower():
            raise ValueError("order identifiers must differ")
        if isinstance(self.size, bool) or not isinstance(self.size, int) or self.size <= 0:
            raise ValueError("fill size must be positive integer micro-contracts")
        if isinstance(self.price, bool) or not isinstance(self.price, int) or not 0 < self.price <= MAX_PRICE_UNITS:
            raise ValueError("fill price must be integer milli-points in (0,100]")
        for a, signature, intent in (
            (self.buy, self.buy_signature, self.buy_intent),
            (self.sell, self.sell_signature, self.sell_intent),
        ):
            if not isinstance(signature, bytes) or not isinstance(intent, bytes):
                raise ValueError("signature and intent must be bytes")
            if "0x" + keccak(intent).hex() != a.order_id.lower():
                raise ValueError("intent preimage does not match signed order identifier")
            if self.size > a.size or not a.min_price <= self.price <= a.max_price:
                raise ValueError("fill exceeds signed size or price bounds")
            if notional_units(a.size, self.price, round_up=False) < MIN_NOTIONAL_UNITS:
                raise ValueError("authorized order is below minimum notional")
            if notional_units(self.size, self.price) > a.max_notional:
                raise ValueError("fill exceeds signed notional budget")

    def contract_tuple(self) -> tuple:
        return (
            tuple(self.buy.message().values()), self.buy_signature,
            tuple(self.sell.message().values()), self.sell_signature,
            self.size, self.price, self.buy_intent, self.sell_intent,
        )


class RelayPending(RuntimeError):
    def __init__(self, tx_hash: str):
        self.tx_hash = tx_hash
        super().__init__(f"Settlement status unknown; reconcile transaction {tx_hash} before retrying")


class RelayReverted(RuntimeError):
    def __init__(self, tx_hash: str):
        self.tx_hash = tx_hash
        super().__init__(f"Atomic settlement reverted: {tx_hash}")


@dataclass(frozen=True)
class RelayConfirmation:
    tx_hash: str
    block_number: int
    match_count: int


@dataclass(frozen=True)
class PendingRelay:
    tx_hash: str
    match_count: int
    raw_transaction: bytes = field(repr=False)
    executor: str
    expected_matches: tuple[tuple, ...]


class RelayJournal(Protocol):
    """REQUIRED durable store, keyed by (chain_id, relayer address).

    record_signed MUST atomically refuse an already outstanding transaction
    across processes, persist before returning, and retain the signed bytes for
    reconciliation. record_receipt must durably record final outcome before
    releasing that slot. No in-memory production fallback is provided.
    """

    def pending(self, chain_id: int, relayer: str) -> PendingRelay | None: ...
    def record_signed(self, chain_id: int, relayer: str, pending: PendingRelay) -> None: ...
    def record_receipt(self, chain_id: int, relayer: str, tx_hash: str, receipt: dict) -> None: ...


class AtomicRelaySubmitter:
    def __init__(self, *, w3, executor_address: str, chain_id: int,
                 relayer_private_key: str, journal: RelayJournal, receipt_timeout: int = 120):
        from eth_account import Account

        if not w3.is_address(executor_address) or int(executor_address, 16) == 0:
            raise ValueError("a deployed V2 executor address is required")
        if isinstance(chain_id, bool) or not isinstance(chain_id, int) or chain_id != 80002:
            raise ValueError("only Polygon Amoy (80002) is supported")
        if receipt_timeout <= 0:
            raise ValueError("receipt timeout must be positive")
        if journal is None:
            raise ValueError("a durable settlement journal is required")
        self._w3 = w3
        self._account = Account.from_key(relayer_private_key)
        self._executor = w3.eth.contract(address=w3.to_checksum_address(executor_address), abi=EXECUTOR_ABI)
        self._chain_id = chain_id
        self._timeout = receipt_timeout
        self._lock = Lock()
        self._journal = journal
        previous = journal.pending(chain_id, self._account.address)
        if previous and previous.executor.lower() != executor_address.lower():
            raise ValueError("pending transaction belongs to a different executor; reconcile it first")
        self._pending = previous.tx_hash if previous else None
        self._pending_count = previous.match_count if previous else 0
        self._expected_matches = previous.expected_matches if previous else ()

    def submit(self, matches: list[AuthorizedMatch]) -> RelayConfirmation:
        if not matches:
            raise ValueError("cannot submit an empty settlement batch")
        with self._lock:
            if self._pending is not None:
                # An RPC timeout is NOT permission to sign the same fills again.
                raise RelayPending(self._pending)
            if self._w3.eth.chain_id != self._chain_id:
                raise ValueError("RPC is connected to the wrong chain")
            if not self._w3.eth.get_code(self._executor.address):
                raise ValueError("V2 executor has no deployed code")

            call = self._executor.functions.executeMatches([m.contract_tuple() for m in matches])
            # Build performs an eth_estimateGas preflight. An unsafe/missing
            # ledger, stale price, wrong signature or insufficient backing must
            # reject before spending gas, not fall back to trader-key settlement.
            transaction = call.build_transaction({
                "from": self._account.address,
                "chainId": self._chain_id,
                "nonce": self._w3.eth.get_transaction_count(self._account.address, "pending"),
            })
            signed = self._account.sign_transaction(transaction)
            # Derive/latch the hash BEFORE sending: the RPC may accept a tx and
            # then disconnect without returning its hash. That is still pending,
            # not a known failure that is safe to resubmit.
            tx_hash = self._w3.to_hex(self._w3.keccak(signed.raw_transaction))
            expected = tuple((
                m.buy.digest(self._chain_id, self._executor.address),
                m.sell.digest(self._chain_id, self._executor.address),
                bytes.fromhex(m.buy.basket_id[2:]),
                m.size, m.price, notional_units(m.size, m.price),
            ) for m in matches)
            self._journal.record_signed(
                self._chain_id, self._account.address,
                PendingRelay(tx_hash, len(matches), bytes(signed.raw_transaction), self._executor.address, expected),
            )
            self._pending = tx_hash
            self._pending_count = len(matches)
            self._expected_matches = expected
            try:
                returned = self._w3.to_hex(self._w3.eth.send_raw_transaction(signed.raw_transaction))
                if returned != tx_hash:
                    raise ValueError("RPC returned a different transaction hash")
            except Exception as exc:
                raise RelayPending(tx_hash) from exc
            try:
                receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=self._timeout)
            except Exception as exc:
                # Keep the durable pending hash latched; never blindly re-sign.
                raise RelayPending(tx_hash) from exc
            return self._confirmed(receipt, tx_hash, len(matches))

    def reconcile_pending(self) -> RelayConfirmation:
        with self._lock:
            if self._pending is None:
                raise ValueError("no pending settlement")
            tx_hash = self._pending
            if self._w3.eth.chain_id != self._chain_id:
                raise RelayPending(tx_hash)
            try:
                receipt = self._w3.eth.get_transaction_receipt(tx_hash)
            except Exception as exc:
                raise RelayPending(tx_hash) from exc
            return self._confirmed(receipt, tx_hash, self._pending_count)

    def _confirmed(self, receipt: dict, tx_hash: str, count: int) -> RelayConfirmation:
        from hexbytes import HexBytes

        if not isinstance(receipt, Mapping):
            raise RelayPending(tx_hash)
        try:
            if bytes(HexBytes(receipt["transactionHash"])) != bytes(HexBytes(tx_hash)):
                raise ValueError("receipt belongs to a different transaction")
        except (KeyError, ValueError, TypeError) as exc:
            raise RelayPending(tx_hash) from exc
        status = receipt.get("status")
        block = receipt.get("blockNumber")
        if type(status) is not int or status not in (0, 1) or type(block) is not int or block < 0:
            raise RelayPending(tx_hash)
        if status == 1:
            from web3.logs import DISCARD

            try:
                events = self._executor.events.MatchExecuted().process_receipt(receipt, errors=DISCARD)
                if any(bytes(HexBytes(event["transactionHash"])) != bytes(HexBytes(tx_hash)) for event in events):
                    raise ValueError("execution log belongs to a different transaction")
                actual = tuple((
                    bytes(event["args"]["buyDigest"]), bytes(event["args"]["sellDigest"]),
                    bytes(event["args"]["basketId"]), event["args"]["size"],
                    event["args"]["price"], event["args"]["notional"],
                ) for event in events if event["address"].lower() == self._executor.address.lower())
                if actual != self._expected_matches or len(actual) != count:
                    raise ValueError("receipt does not prove every submitted matched fill")
            except Exception as exc:
                # Receipt status 1 alone is insufficient: a wrong address or
                # no-op contract must not masquerade as settled positions.
                raise RelayPending(tx_hash) from exc
        try:
            self._journal.record_receipt(self._chain_id, self._account.address, tx_hash, receipt)
        except Exception as exc:
            # Even a mined tx must not be reported as reconciled while its
            # durable coordinator record still says pending.
            raise RelayPending(tx_hash) from exc
        self._pending = None
        self._pending_count = 0
        self._expected_matches = ()
        if receipt["status"] != 1:
            raise RelayReverted(tx_hash)
        return RelayConfirmation(tx_hash, int(receipt["blockNumber"]), count)
