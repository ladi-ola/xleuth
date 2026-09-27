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
class SLTPOrderRequest(BaseOrderRequest):
    order_type: Literal[OrderType.STOP_LOSS, OrderType.TAKE_PROFIT]
    trigger_price: float = Field(gt=0)
    position_id: str
    max_slippage_bps: int = Field(ge=0, le=10000)
    oco_group_id: Optional[str] = None  # For OCO pairing


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