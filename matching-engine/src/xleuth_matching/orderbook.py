"""Per-basket price-time priority limit order books with market order support.

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
    TRIGGERED = "triggered"


class OrderType(str, Enum):
    LIMIT = "limit"
    MARKET = "market"
    STOP = "stop"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


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
    price: float  # For limit orders; ignored for market/stop/SL-TP orders
    size: float
    leverage: int
    order_type: OrderType = OrderType.LIMIT
    max_slippage_bps: int = 0  # For market/stop/SL-TP orders: max slippage in basis points
    trigger_price: float = 0.0  # For stop/SL-TP orders: trigger price
    position_id: str = ""  # For SL/TP orders: attached position ID
    oco_group_id: str = ""  # For OCO pairing: links SL and TP orders
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
        self._stop_orders: dict[str, OrderRecord] = {}  # Stop orders waiting for trigger
        self._sltp_orders: dict[str, OrderRecord] = {}  # SL/TP orders waiting for trigger
        self._oco_groups: dict[str, tuple[str, str]] = {}  # oco_group_id -> (sl_order_id, tp_order_id)

    # ── Order placement / cancellation ────────────────────────────────────

    def place(self, order: OrderRecord) -> PlacementResult:
        """Place a limit order (price-time priority, can rest)."""
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

    def place_market(self, order: OrderRecord) -> PlacementResult:
        """Place a market order (FOK with slippage guard).
        
        Market orders must fill completely immediately or be rejected.
        The max_slippage_bps defines the worst acceptable price:
        - BUY: worst price = best_ask * (1 + max_slippage_bps / 10000)
        - SELL: worst price = best_bid * (1 - max_slippage_bps / 10000)
        """
        if not order.rest() and order.status != OrderStatus.REJECTED:
            raise ValueError(f"Order {order.order_id} is not placeable in status {order.status}")
        result = PlacementResult(order=order)

        if order.order_type != OrderType.MARKET:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = "not a market order"
            result.error = order.rejection_reason
            return result

        if order.max_slippage_bps < 0 or order.max_slippage_bps > 10000:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = "invalid_slippage_bps"
            result.error = order.rejection_reason
            return result

        # Get current book depth
        bids, asks = self.depth()
        best_bid = bids[0][0] if bids else None
        best_ask = asks[0][0] if asks else None

        # Determine worst acceptable price based on slippage guard
        if order.side is Side.BUY:
            if best_ask is None:
                order.status = OrderStatus.REJECTED
                order.rejection_reason = "no_liquidity"
                result.error = "no_liquidity: no asks available"
                return result
            # For buy, worst price is best_ask + slippage
            worst_price = best_ask * (1 + order.max_slippage_bps / 10000)
            available_liquidity = sum(size for price, size in asks if price <= worst_price)
        else:  # SELL
            if best_bid is None:
                order.status = OrderStatus.REJECTED
                order.rejection_reason = "no_liquidity"
                result.error = "no_liquidity: no bids available"
                return result
            # For sell, worst price is best_bid - slippage
            worst_price = best_bid * (1 - order.max_slippage_bps / 10000)
            available_liquidity = sum(size for price, size in bids if price >= worst_price)

        # FOK: check if full size can be filled within slippage
        if available_liquidity + 1e-9 < order.size:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = "insufficient_liquidity"
            result.error = f"insufficient_liquidity: need {order.size}, available {available_liquidity} within slippage guard"
            return result

        # Self-trade guard for market orders
        try:
            self._guard_self_trade_market(order, worst_price)
        except SelfTradeError as exc:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = str(exc)
            result.error = str(exc)
            return result

        # Execute market order by walking the book
        now = _now_naive()
        self._orders[order.order_id] = order
        
        fills = self._execute_market_order(order, worst_price, now)
        
        # Verify full fill (FOK)
        total_filled = sum(f.size for f in fills)
        if total_filled + 1e-9 < order.size:
            # Should not happen if we checked liquidity, but safety check
            order.status = OrderStatus.REJECTED
            order.rejection_reason = "fok_failed"
            result.error = "fok_failed: could not fill full size"
            # Clean up any partial fills (shouldn't happen with FOK)
            for fill in fills:
                maker = self._orders.get(fill.maker_order_id)
                if maker:
                    maker.filled_size = round(maker.filled_size - fill.size, 6)
                    if maker.filled_size <= 1e-9:
                        maker.status = OrderStatus.OPEN
            return result

        order.filled_size = total_filled
        order.status = OrderStatus.FILLED
        result.fills = fills
        return result

    def place_stop(self, order: OrderRecord) -> PlacementResult:
        """Place a stop order (GTC, converts to market order when triggered).
        
        Stop orders are stored separately and evaluated against mark/index price.
        - BUY stop: triggers when mark_price >= trigger_price (breakout entry long)
        - SELL stop: triggers when mark_price <= trigger_price (breakout entry short)
        
        Margin is reserved at placement time (same as limit orders).
        """
        if not order.rest() and order.status != OrderStatus.REJECTED:
            raise ValueError(f"Order {order.order_id} is not placeable in status {order.status}")
        result = PlacementResult(order=order)

        if order.order_type != OrderType.STOP:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = "not a stop order"
            result.error = order.rejection_reason
            return result

        if order.trigger_price <= 0:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = "invalid_trigger_price"
            result.error = order.rejection_reason
            return result

        if order.max_slippage_bps < 0 or order.max_slippage_bps > 10000:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = "invalid_slippage_bps"
            result.error = order.rejection_reason
            return result

        # Store stop order (does not go into the matching engine book)
        self._stop_orders[order.order_id] = order
        order.status = OrderStatus.OPEN
        return result

    def check_triggers(self, mark_price: float) -> list[PlacementResult]:
        """Evaluate all stop orders against the current mark/index price.
        
        Returns list of PlacementResults for triggered stop orders that were
        converted to market orders and executed.
        """
        triggered_results: list[PlacementResult] = []
        to_remove: list[str] = []

        for order_id, order in self._stop_orders.items():
            should_trigger = False
            if order.side is Side.BUY and mark_price >= order.trigger_price:
                should_trigger = True
            elif order.side is Side.SELL and mark_price <= order.trigger_price:
                should_trigger = True

            if should_trigger:
                # Convert to market order and execute
                to_remove.append(order_id)
                market_order = OrderRecord(
                    order_id=order_id,
                    basket_name=order.basket_name,
                    trader=order.trader,
                    side=order.side,
                    price=0.0,  # Market order
                    size=order.size,
                    leverage=order.leverage,
                    order_type=OrderType.MARKET,
                    max_slippage_bps=order.max_slippage_bps,
                    trigger_price=order.trigger_price,
                )
                # Remove from stop orders before executing
                self._stop_orders.pop(order_id, None)
                # Execute as market order (FOK with slippage)
                result = self.place_market(market_order)
                # Update the original stop order's status
                if result.success:
                    order.status = OrderStatus.TRIGGERED
                    order.filled_size = result.order.filled_size
                else:
                    order.status = OrderStatus.REJECTED
                    order.rejection_reason = result.error
                # Put back in _orders for query purposes
                self._orders[order_id] = order
                triggered_results.append(result)

        return triggered_results

    def cancel_stop(self, order_id: str) -> OrderRecord | None:
        """Cancel a resting stop order."""
        order = self._stop_orders.pop(order_id, None)
        if order is None:
            # Also check regular orders in case it was already triggered
            order = self._orders.get(order_id)
            if order is not None and order.order_type == OrderType.STOP:
                if order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.TRIGGERED):
                    raise ValueError(f"Order {order_id} is {order.status} and cannot be cancelled")
                order.status = OrderStatus.CANCELLED
            return order
        order.status = OrderStatus.CANCELLED
        return order

    def get_stop_order(self, order_id: str) -> OrderRecord | None:
        """Get a stop order by ID (checks both pending and triggered)."""
        # Check pending stop orders first
        order = self._stop_orders.get(order_id)
        if order is not None:
            return order
        # Check triggered/completed stop orders
        order = self._orders.get(order_id)
        if order is not None and order.order_type == OrderType.STOP:
            return order
        return None

    def get_all_stop_orders(self) -> list[OrderRecord]:
        """Get all stop orders (pending + triggered)."""
        return list(self._stop_orders.values()) + [
            o for o in self._orders.values() if o.order_type == OrderType.STOP
        ]

    # ── SL/TP Order Methods ─────────────────────────────────────────────────

    def place_sltp(self, order: OrderRecord) -> PlacementResult:
        """Place a stop-loss or take-profit order (attached to a position, OCO).
        
        SL/TP orders are attached to an existing position and trigger on mark price.
        - STOP_LOSS: triggers when mark price moves against the position
        - TAKE_PROFIT: triggers when mark price moves in favor of the position
        
        Both are full-close only (size = position size). OCO: when one triggers, 
        the other is automatically cancelled.
        
        No additional margin reservation (position already has margin locked).
        """
        if not order.rest() and order.status != OrderStatus.REJECTED:
            raise ValueError(f"Order {order.order_id} is not placeable in status {order.status}")
        result = PlacementResult(order=order)

        if order.order_type not in (OrderType.STOP_LOSS, OrderType.TAKE_PROFIT):
            order.status = OrderStatus.REJECTED
            order.rejection_reason = "not an SL/TP order"
            result.error = order.rejection_reason
            return result

        if not order.position_id:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = "position_id required for SL/TP orders"
            result.error = order.rejection_reason
            return result

        if order.trigger_price <= 0:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = "invalid_trigger_price"
            result.error = order.rejection_reason
            return result

        if order.max_slippage_bps < 0 or order.max_slippage_bps > 10000:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = "invalid_slippage_bps"
            result.error = order.rejection_reason
            return result

        # Store SL/TP order
        self._sltp_orders[order.order_id] = order
        order.status = OrderStatus.OPEN

        # Handle OCO pairing
        if order.oco_group_id:
            if order.oco_group_id not in self._oco_groups:
                self._oco_groups[order.oco_group_id] = (order.order_id, "")
            else:
                sl_id, tp_id = self._oco_groups[order.oco_group_id]
                if order.order_type == OrderType.STOP_LOSS:
                    self._oco_groups[order.oco_group_id] = (order.order_id, tp_id)
                else:
                    self._oco_groups[order.oco_group_id] = (sl_id, order.order_id)

        return result

    def check_sltp_triggers(self, mark_price: float) -> list[PlacementResult]:
        """Evaluate all SL/TP orders against the current mark/index price.
        
        Returns list of PlacementResults for triggered SL/TP orders that were
        converted to market orders and executed.
        """
        triggered_results: list[PlacementResult] = []

        # Collect orders to evaluate first to avoid modifying dict during iteration
        orders_to_check = list(self._sltp_orders.items())

        for order_id, order in orders_to_check:
            should_trigger = False
            
            # For SL/TP, the trigger logic depends on the position side:
            # - If position is LONG (side=BUY): SL triggers when price <= trigger, TP triggers when price >= trigger
            # - If position is SHORT (side=SELL): SL triggers when price >= trigger, TP triggers when price <= trigger
            # The order.side indicates the close direction (opposite of position side)
            if order.order_type == OrderType.STOP_LOSS:
                # Stop-loss: triggers when price moves against position
                if order.side is Side.SELL and mark_price <= order.trigger_price:
                    # Long position, stop-loss sell triggers when price drops
                    should_trigger = True
                elif order.side is Side.BUY and mark_price >= order.trigger_price:
                    # Short position, stop-loss buy triggers when price rises
                    should_trigger = True
            elif order.order_type == OrderType.TAKE_PROFIT:
                # Take-profit: triggers when price moves in favor of position
                if order.side is Side.SELL and mark_price >= order.trigger_price:
                    # Long position, take-profit sell triggers when price rises
                    should_trigger = True
                elif order.side is Side.BUY and mark_price <= order.trigger_price:
                    # Short position, take-profit buy triggers when price drops
                    should_trigger = True

            if should_trigger:
                market_order = OrderRecord(
                    order_id=order_id,
                    basket_name=order.basket_name,
                    trader=order.trader,
                    side=order.side,
                    price=0.0,  # Market order
                    size=order.size,
                    leverage=order.leverage,
                    order_type=OrderType.MARKET,
                    max_slippage_bps=order.max_slippage_bps,
                    trigger_price=order.trigger_price,
                    position_id=order.position_id,
                    oco_group_id=order.oco_group_id,
                )
                # Remove from SL/TP orders before executing
                self._sltp_orders.pop(order_id, None)
                # Execute as market order (FOK with slippage)
                result = self.place_market(market_order)
                # Update the original SL/TP order's status
                if result.success:
                    order.status = OrderStatus.TRIGGERED
                    order.filled_size = result.order.filled_size
                    
                    # OCO: Cancel the sibling order
                    if order.oco_group_id and order.oco_group_id in self._oco_groups:
                        sl_id, tp_id = self._oco_groups[order.oco_group_id]
                        sibling_id = tp_id if order.order_type == OrderType.STOP_LOSS else sl_id
                        if sibling_id and sibling_id in self._sltp_orders:
                            sibling = self._sltp_orders.pop(sibling_id)
                            sibling.status = OrderStatus.CANCELLED
                            sibling.rejection_reason = "oco_cancelled"
                            self._orders[sibling_id] = sibling
                else:
                    order.status = OrderStatus.REJECTED
                    order.rejection_reason = result.error
                # Put back in _orders for query purposes
                self._orders[order_id] = order
                triggered_results.append(result)

        return triggered_results

    def cancel_sltp(self, order_id: str) -> OrderRecord | None:
        """Cancel a resting SL/TP order."""
        order = self._sltp_orders.pop(order_id, None)
        if order is None:
            # Also check regular orders in case it was already triggered
            order = self._orders.get(order_id)
            if order is not None and order.order_type in (OrderType.STOP_LOSS, OrderType.TAKE_PROFIT):
                if order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.TRIGGERED):
                    raise ValueError(f"Order {order_id} is {order.status} and cannot be cancelled")
                order.status = OrderStatus.CANCELLED
            return order
        order.status = OrderStatus.CANCELLED
        
        # OCO: Also cancel sibling
        if order.oco_group_id and order.oco_group_id in self._oco_groups:
            sl_id, tp_id = self._oco_groups[order.oco_group_id]
            sibling_id = tp_id if order.order_type == OrderType.STOP_LOSS else sl_id
            if sibling_id and sibling_id in self._sltp_orders:
                sibling = self._sltp_orders.pop(sibling_id)
                sibling.status = OrderStatus.CANCELLED
                sibling.rejection_reason = "oco_cancelled"
                self._orders[sibling_id] = sibling
        
        return order

    def get_sltp_order(self, order_id: str) -> OrderRecord | None:
        """Get an SL/TP order by ID (checks both pending and triggered)."""
        # Check pending SL/TP orders first
        order = self._sltp_orders.get(order_id)
        if order is not None:
            return order
        # Check triggered/completed SL/TP orders
        order = self._orders.get(order_id)
        if order is not None and order.order_type in (OrderType.STOP_LOSS, OrderType.TAKE_PROFIT):
            return order
        return None

    def cancel(self, order_id: str) -> OrderRecord:
        # Check regular orders first
        record = self._orders.get(order_id)
        if record is not None:
            if record.status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED):
                raise ValueError(f"Order {order_id} is {record.status} and cannot be cancelled")
            if record.order_type == OrderType.STOP:
                # Stop order that was already triggered
                record.status = OrderStatus.CANCELLED
                return record
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

        # Check pending stop orders
        record = self._stop_orders.get(order_id)
        if record is not None:
            if record.status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.TRIGGERED):
                raise ValueError(f"Order {order_id} is {record.status} and cannot be cancelled")
            record.status = OrderStatus.CANCELLED
            self._stop_orders.pop(order_id, None)
            # Add to _orders so it can be queried after cancellation
            self._orders[order_id] = record
            return record

        # Check pending SL/TP orders
        record = self._sltp_orders.get(order_id)
        if record is not None:
            if record.status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.TRIGGERED):
                raise ValueError(f"Order {order_id} is {record.status} and cannot be cancelled")
            record.status = OrderStatus.CANCELLED
            self._sltp_orders.pop(order_id, None)
            # Add to _orders so it can be queried after cancellation
            self._orders[order_id] = record
            
            # OCO: Also cancel sibling
            if record.oco_group_id and record.oco_group_id in self._oco_groups:
                sl_id, tp_id = self._oco_groups[record.oco_group_id]
                sibling_id = tp_id if record.order_type == OrderType.STOP_LOSS else sl_id
                if sibling_id and sibling_id in self._sltp_orders:
                    sibling = self._sltp_orders.pop(sibling_id)
                    sibling.status = OrderStatus.CANCELLED
                    sibling.rejection_reason = "oco_cancelled"
                    self._orders[sibling_id] = sibling
            return record

        raise KeyError(f"Unknown order {order_id}")

    def get_order(self, order_id: str) -> OrderRecord | None:
        # Check regular orders first
        order = self._orders.get(order_id)
        if order is not None:
            return order
        # Check pending stop orders
        order = self._stop_orders.get(order_id)
        if order is not None:
            return order
        # Check pending SL/TP orders
        return self._sltp_orders.get(order_id)

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

    def _guard_self_trade_market(self, incoming: OrderRecord, worst_price: float) -> None:
        """Reject a market order that would cross the same trader's own resting order within slippage."""
        opposite_side = self._book.offers if incoming.side is Side.BUY else self._book.bids
        for price, orders in (opposite_side or {}).items():
            for rest in orders or []:
                if rest.trader_id != incoming.trader:
                    continue
                if incoming.side is Side.BUY and price <= worst_price:
                    raise SelfTradeError(
                        f"self_trade: market buy would match own resting ask at {price} (worst: {worst_price})"
                    )
                if incoming.side is Side.SELL and price >= worst_price:
                    raise SelfTradeError(
                        f"self_trade: market sell would match own resting bid at {price} (worst: {worst_price})"
                    )

    def _execute_market_order(self, order: OrderRecord, worst_price: float, now: datetime) -> list[Fill]:
        """Execute a market order by walking the book up to worst_price.
        
        Returns list of fills. Modifies the underlying engine's book directly.
        """
        fills: list[Fill] = []
        remaining = order.size
        
        # Determine which side of the book to match against
        if order.side is Side.BUY:
            # Buy matches against asks (sell orders)
            book_side = self._book.offers
            price_levels = sorted(book_side.keys()) if book_side else []
            price_check = lambda p: p <= worst_price
        else:
            # Sell matches against bids (buy orders)
            book_side = self._book.bids
            price_levels = sorted(book_side.keys(), reverse=True) if book_side else []
            price_check = lambda p: p >= worst_price

        for price in price_levels:
            if not price_check(price):
                break
            if remaining <= 1e-9:
                break
            
            orders_at_price = list(book_side.get(price, []))
            for resting_order in orders_at_price:
                if remaining <= 1e-9:
                    break
                
                # Skip self-trade (already checked, but safety)
                if resting_order.trader_id == order.trader:
                    continue
                
                fill_size = min(remaining, resting_order.size)
                
                # Create a trade by placing a crossing limit order at the resting price
                engine_order = Order(
                    side=order.side.to_engine(),
                    price=price,
                    size=fill_size,
                    timestamp=now,
                    order_id=order.order_id,
                    trader_id=order.trader,
                    execution=Execution.LIMIT,
                    price_number_of_digits=2,
                )
                
                # Place the crossing order and match
                self._engine.place(Orders([engine_order]))
                trades = self._engine.match(now)
                
                for trade in trades.trades:
                    # Update registry
                    maker = self._orders.get(trade.book_order_id)
                    if maker is None:
                        logger.warning("Trade %s references unknown resting order %s", trade.trade_id, trade.book_order_id)
                        continue
                    
                    taker_size = float(trade.size)
                    order.filled_size = round(order.filled_size + taker_size, 6)
                    maker.filled_size = round(maker.filled_size + taker_size, 6)
                    
                    if maker.remaining <= 1e-9:
                        maker.status = OrderStatus.FILLED
                    elif maker.filled_size > 0:
                        maker.status = OrderStatus.PARTIALLY_FILLED
                    
                    fills.append(
                        Fill(
                            trade_id=trade.trade_id,
                            basket_name=self.basket_name,
                            price=float(trade.price),
                            size=float(trade.size),
                            timestamp=trade.timestamp,
                            taker_order_id=order.order_id,
                            maker_order_id=maker.order_id,
                            taker_trader=order.trader,
                            maker_trader=maker.trader,
                            taker_side=order.side,
                            maker_side=order.side.opposite(),
                            taker_leverage=order.leverage,
                            maker_leverage=maker.leverage,
                        )
                    )
                    remaining -= taker_size
                
                # If resting order is fully filled, it's removed from book by engine
                # If partially filled, it stays with reduced size
        
        return fills

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