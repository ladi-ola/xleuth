"""Shared order schemas for all services."""

from datetime import datetime
from enum import Enum
from typing import Optional, Literal, List

from pydantic import BaseModel, Field


class OrderType(str, Enum):
    LIMIT = "limit"
    MARKET = "market"
    STOP = "stop"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    TRIGGERED = "triggered"


class RejectionCode(str, Enum):
    """Machine-readable rejection codes for 422 errors."""
    ORACLE_PRICE_STALE = "oracle_price_stale"
    INSUFFICIENT_MARGIN = "insufficient_margin"
    BASKET_NOT_TRADEABLE = "basket_not_tradeable"
    PRICE_NOT_ON_TICK = "price_not_on_tick"
    SIZE_BELOW_MIN = "size_below_min"
    LEVERAGE_OUT_OF_RANGE = "leverage_out_of_range"
    LEVERAGE_ABOVE_CAP = "leverage_above_cap"
    ORACLE_PRICE_ZERO = "oracle_price_zero"
    UNKNOWN_BASKET = "unknown_basket"
    MAX_SLIPPAGE_BPS_REQUIRED = "max_slippage_bps_required"
    TRIGGER_PRICE_REQUIRED = "trigger_price_required"
    POSITION_ID_REQUIRED = "position_id_required"
    PRICE_REQUIRED_FOR_LIMIT_ORDERS = "price_required_for_limit_orders"
    SL_TP_FIELD_MISMATCH = "sl_tp_field_mismatch"
    POSITION_NOT_FOUND = "position_not_found"
    NO_LIQUIDITY = "no_liquidity"
    INSUFFICIENT_LIQUIDITY = "insufficient_liquidity"
    FOK_FAILED = "fok_failed"
    SELF_TRADE = "self_trade"
    ORACLE_UNREADABLE = "oracle_unreadable"
    LEVERAGE_CAP_UNREADABLE = "leverage_cap_unreadable"
    INVALID_SLIPPAGE_BPS = "invalid_slippage_bps"
    INVALID_TRIGGER_PRICE = "invalid_trigger_price"
    SETTLEMENT_FAILED = "settlement_failed"
    OCO_CANCELLED = "oco_cancelled"


# Base order request
class BaseOrderRequest(BaseModel):
    basket_name: str
    side: OrderSide
    size: float = Field(gt=0)
    leverage: int = Field(ge=1)
    order_type: OrderType = OrderType.LIMIT


# Limit order (existing)
class LimitOrderRequest(BaseOrderRequest):
    order_type: Literal[OrderType.LIMIT] = OrderType.LIMIT
    price: float = Field(gt=0)


# Market order (FOK + slippage guard)
class MarketOrderRequest(BaseOrderRequest):
    order_type: Literal[OrderType.MARKET] = OrderType.MARKET
    max_slippage_bps: int = Field(ge=0, le=10000, description="Max slippage in basis points (0-10000)")


# Stop order (standalone, GTC, converts to market on trigger)
class StopOrderRequest(BaseOrderRequest):
    order_type: Literal[OrderType.STOP] = OrderType.STOP
    trigger_price: float = Field(gt=0)
    max_slippage_bps: int = Field(ge=0, le=10000)


# Stop-Loss / Take-Profit (attached to position, OCO)
# side, size, leverage are optional - derived from position if omitted
# If provided, they must match the position's values
class SLTPOrderRequest(BaseOrderRequest):
    order_type: Literal[OrderType.STOP_LOSS, OrderType.TAKE_PROFIT]
    trigger_price: float = Field(gt=0)
    position_id: str
    max_slippage_bps: int = Field(ge=0, le=10000)
    oco_group_id: Optional[str] = None  # For OCO pairing
    side: Optional[OrderSide] = None
    size: Optional[float] = None
    leverage: Optional[int] = None


# Union of all order request types
OrderRequest = LimitOrderRequest | MarketOrderRequest | StopOrderRequest | SLTPOrderRequest


# Fill response
class FillResponse(BaseModel):
    trade_id: str
    basket_name: str
    price: float
    size: float
    taker_order_id: str
    maker_order_id: str
    taker_trader: str
    maker_trader: str
    taker_side: str
    maker_side: str
    notional: float
    confirmed: bool
    tx_hash: Optional[str] = None
    error: Optional[str] = None
    ts: str


# Margin check response
class MarginCheckResponse(BaseModel):
    ok: bool
    reason: Optional[str] = None
    details: dict = {}


# Order response
class OrderResponse(BaseModel):
    order_id: str
    basket_name: str
    trader: str
    side: str
    order_type: OrderType
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    size: float
    filled_size: float
    remaining: float
    leverage: int
    status: OrderStatus
    rejection_reason: Optional[str] = None
    created_at: str
    fills: List[FillResponse] = []
    failed_fills: List[FillResponse] = []
    margin_check: Optional[MarginCheckResponse] = None
    position_id: Optional[str] = None
    oco_group_id: Optional[str] = None
    average_fill_price: Optional[float] = None


# Cancel response
class CancelResponse(BaseModel):
    order_id: str
    status: OrderStatus
    message: str


# Order book depth snapshot
class BookLevel(BaseModel):
    price: float
    size: float


class BookSnapshot(BaseModel):
    basket_name: str
    bids: List[BookLevel]
    asks: List[BookLevel]
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    mid_price: Optional[float] = None
    spread: Optional[float] = None
    ts: str


# Orders list response
class OrderListItem(BaseModel):
    order_id: str
    basket_name: str
    side: str
    order_type: OrderType
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    size: float
    filled_size: float
    remaining: float
    leverage: int
    status: OrderStatus
    rejection_reason: Optional[str] = None
    created_at: str
    updated_at: str
    position_id: Optional[str] = None
    oco_group_id: Optional[str] = None
    average_fill_price: Optional[float] = None


class OrderListResponse(BaseModel):
    orders: List[OrderListItem] = []
    cursor: Optional[str] = None
    has_more: bool = False


# Position response
class PositionResponse(BaseModel):
    position_id: str
    basket_name: str
    side: str  # "long" or "short"
    size: float
    leverage: int
    entry_price: float
    mark_price: float
    margin_usdc: float
    liquidation_price: Optional[float] = None
    unrealized_pnl_abs: float
    unrealized_pnl_pct: float
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    stop_loss_order_id: Optional[str] = None
    take_profit_order_id: Optional[str] = None
    oco_group_id: Optional[str] = None
    fee_paid: Optional[float] = None
    opened_at: str


class PositionsResponse(BaseModel):
    positions: List[PositionResponse] = []


# Portfolio summary response
class PortfolioSummaryResponse(BaseModel):
    total_balance: float
    free_margin: float
    used_margin: float
    unrealized_pnl: float
    realized_pnl: float


# Candles response
class Candle(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float


class CandlesResponse(BaseModel):
    basket_name: str
    interval: str
    candles: List[Candle] = []


# Basket with 24h change
class BasketPriceResponseWithChange(BaseModel):
    basket_name: str
    index_price: Optional[float] = None
    scaled_price: Optional[float] = None
    computed_at: Optional[str] = None
    constituent_count: Optional[int] = None
    status: str = "active"
    is_tradeable: bool = True
    change_24h_abs: Optional[float] = None
    change_24h_pct: Optional[float] = None