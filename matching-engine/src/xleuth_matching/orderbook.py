"""Per-basket price-time priority limit order books.

Extends the `order-matching` PyPI package (v0.12.0) rather than writing a
matching engine from scratch: each BasketOrderBook wraps a MatchingEngine
whose `unprocessed_orders` book is the resting limit-order structure (bids/
asks are sorted by price with time priority preserved per level, and
`match(timestamp)` produces ExecutedTrades with incoming/resting order ids).

Why `order-matching` and not `dyn4mik3/OrderBook`: the latter's PyPI release
(`orderbook 0.1.2`) is broken on import (circular import in __init__.py),
while `order-matching` installs cleanly, implements the same price-time
priority semantics and exposes cancel + partial-fill behavior we verified in
tests before wiring it up.

The wrapper adds what the engine lacks: order metadata (trader wallet,
leverage, basket, status, filled size) kept in an engine-side registry, a
self-trade guard (an order that would cross the same trader's own resting
order is rejected), and a depth snapshot for the WebSocket/book API.
Limit orders only (market/stop orders are explicitly out of scope for v1);
orders are GTC (no expiration) — matching the dated-basket lifecycle.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from order_matching.enums import Execution, Side as EngineSide, Status as EngineStatus
from order_matching.matching_engine import MatchingEngine
from order_matching.orders import Order, Orders

logger = logging.getLogger("xleuth_matching.orderbook")

# order-matching's engine compares naive datetimes internally; use naive UTC.
def _now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class OrderStatus(str, Enum):
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"

    def to_engine(self) -> EngineSide:
        return EngineSide.BUY if self is Side.BUY else EngineSide.SELL

    def opposite(self) -> "Side":
        return Side.SELL if self is Side.BUY else Side.BUY


@dataclass
class OrderRecord:
    order_id: str
    basket_name: str
    trader: str
    side: Side
    price: float
    size: float
    leverage: int
    status: OrderStatus = OrderStatus.OPEN
    filled_size: float = 0.0
    rejection_reason: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def remaining(self) -> float:
        return round(self.size - self.filled_size, 6)

    def rest(self) -> bool:
        return self.status in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)


@dataclass
class Fill:
    trade_id: str
    basket_name: str
    price: float
    size: float
    timestamp: datetime
    taker_order_id: str
    maker_order_id: str
    taker_trader: str
    maker_trader: str
    taker_side: Side
    maker_side: Side
    taker_leverage: int
    maker_leverage: int

    @property
    def fee(self) -> float:
        """Platform fee in index-point units is not on-chain in v1; the fee
        basis points are applied to the notional at the engine layer when
        reporting (see service API). Kept as a pure property for now."""

    @property
    def notional(self) -> float:
        return self.price * self.size


@dataclass
class PlacementResult:
    order: OrderRecord
    fills: list[Fill] = field(default_factory=list)
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None


class SelfTradeError(ValueError):
    """Raised when an incoming order would cross the same trader's resting order."""


class BasketOrderBook:
    """One price-time priority limit order book per basket_id."""

    def __init__(self, basket_name: str, seed: int = 1):
        self.basket_name = basket_name
        self._engine = MatchingEngine(seed=seed)
        self._book = self._engine.unprocessed_orders
        self._orders: dict[str, OrderRecord] = {}

    # ── Order placement / cancellation ────────────────────────────────────

    def place(self, order: OrderRecord) -> PlacementResult:
        if not order.rest() and order.status != OrderStatus.REJECTED:
            raise ValueError(f"Order {order.order_id} is not placeable in status {order.status}")
        result = PlacementResult(order=order)
        try:
            self._guard_self_trade(order)
        except SelfTradeError as exc:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = str(exc)
            result.error = str(exc)
            return result

        now = _now_naive()
        self._orders[order.order_id] = order
        engine_order = Order(
            side=order.side.to_engine(),
            price=order.price,
            size=order.size,
            timestamp=now,
            order_id=order.order_id,
            trader_id=order.trader,
            execution=Execution.LIMIT,
            price_number_of_digits=2,
        )
        try:
            self._engine.place(Orders([engine_order]))
            trades = self._engine.match(now)
        except Exception as exc:
            logger.exception("Place failed for %s", order.order_id)
            self._orders.pop(order.order_id, None)
            order.status = OrderStatus.REJECTED
            order.rejection_reason = f"engine error: {exc}"
            result.error = order.rejection_reason
            return result

        for trade in trades.trades:
            self._apply_trade(order, trade)
        result.fills = self._settle_own_trades(order, trades.trades)
        return result

    def cancel(self, order_id: str) -> OrderRecord:
        record = self._orders.get(order_id)
        if record is None:
            raise KeyError(f"Unknown order {order_id}")
        if record.status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED):
            raise ValueError(f"Order {order_id} is {record.status} and cannot be cancelled")
        now = _now_naive()
        cancel = Order(
            side=record.side.to_engine(),
            price=record.price,
            size=0.0,
            timestamp=now,
            order_id=order_id,
            trader_id=record.trader,
            execution=Execution.LIMIT,
            status=EngineStatus.CANCEL,
        )
        self._engine.place(Orders([cancel]))
        self._engine.match(now)
        record.status = OrderStatus.CANCELLED
        return record

    def get_order(self, order_id: str) -> OrderRecord | None:
        return self._orders.get(order_id)

    # ── Snapshot / depth ──────────────────────────────────────────────────

    def snapshot(self) -> dict:
        bids, asks = self.depth()
        best_bid = bids[0][0] if bids else None
        best_ask = asks[0][0] if asks else None
        mid = None
        if best_bid is not None and best_ask is not None:
            mid = round((best_bid + best_ask) / 2, 4)
        elif best_bid is not None:
            mid = best_bid
        elif best_ask is not None:
            mid = best_ask
        spread = round(best_ask - best_bid, 4) if best_bid is not None and best_ask is not None else None
        return {
            "basket_name": self.basket_name,
            "bids": bids,
            "asks": asks,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid_price": mid,
            "spread": spread,
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    def depth(self, levels: int = 20) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
        """Aggregated (price, total size) levels, best price first."""
        bids_raw = self._book.bids_depth or []
        asks_raw = self._book.asks_depth or []
        bids = [(round(float(p), 6), round(float(s), 6)) for p, s in bids_raw[:levels]]
        asks = [(round(float(p), 6), round(float(s), 6)) for p, s in asks_raw[:levels]]
        return bids, asks

    # ── Internals ─────────────────────────────────────────────────────────

    def _guard_self_trade(self, incoming: OrderRecord) -> None:
        """Reject an order that would cross the same trader's own resting order."""
        opposite_side = self._book.offers if incoming.side is Side.BUY else self._book.bids
        for price, orders in (opposite_side or {}).items():
            for rest in orders or []:
                if rest.trader_id != incoming.trader:
                    continue
                if incoming.side is Side.BUY and price <= incoming.price:
                    raise SelfTradeError(
                        f"self_trade: buy {incoming.price} would match own resting ask at {price}"
                    )
                if incoming.side is Side.SELL and price >= incoming.price:
                    raise SelfTradeError(
                        f"self_trade: sell {incoming.price} would match own resting bid at {price}"
                    )

    def _apply_trade(self, incoming: OrderRecord, trade) -> None:
        """Update registry statuses/filled sizes for both sides of a trade."""
        maker = self._orders.get(trade.book_order_id)
        taker_size = float(trade.size)

        incoming.filled_size = round(incoming.filled_size + taker_size, 6)
        if incoming.remaining <= 1e-9:
            incoming.status = OrderStatus.FILLED
        elif incoming.filled_size > 0:
            incoming.status = OrderStatus.PARTIALLY_FILLED

        if maker is not None:
            maker.filled_size = round(maker.filled_size + taker_size, 6)
            if maker.remaining <= 1e-9:
                maker.status = OrderStatus.FILLED
            elif maker.filled_size > 0:
                maker.status = OrderStatus.PARTIALLY_FILLED

    def _settle_own_trades(self, incoming: OrderRecord, trades) -> list[Fill]:
        fills: list[Fill] = []
        for trade in trades:
            maker = self._orders.get(trade.book_order_id)
            if maker is None:
                logger.warning("Trade %s references unknown resting order %s", trade.trade_id, trade.book_order_id)
                continue
            fills.append(
                Fill(
                    trade_id=trade.trade_id,
                    basket_name=self.basket_name,
                    price=float(trade.price),
                    size=float(trade.size),
                    timestamp=trade.timestamp,
                    taker_order_id=incoming.order_id,
                    maker_order_id=maker.order_id,
                    taker_trader=incoming.trader,
                    maker_trader=maker.trader,
                    taker_side=incoming.side,
                    maker_side=incoming.side.opposite(),
                    taker_leverage=incoming.leverage,
                    maker_leverage=maker.leverage,
                )
            )
        return fills


class OrderBookManager:
    """One BasketOrderBook per basket_name."""

    def __init__(self, baskets: list[str] | None = None):
        self._books: dict[str, BasketOrderBook] = {}
        for name in baskets or []:
            self._books[name] = BasketOrderBook(name)

    def get(self, basket_name: str) -> BasketOrderBook:
        book = self._books.get(basket_name)
        if book is None:
            book = BasketOrderBook(basket_name)
            self._books[basket_name] = book
        return book

    def names(self) -> list[str]:
        return sorted(self._books)
