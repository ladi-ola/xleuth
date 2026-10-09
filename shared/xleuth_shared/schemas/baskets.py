from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class ConstituentMarket(BaseModel):
    condition_id: str | None = None
    clob_token_id: str | None = None
    event_id: str | None = None
    question: str | None = None
    end_date: str | None = None
    price: float | None = None
    volume: float = 0.0
    price_source: str | None = None
    sub_markets: list["ConstituentSubMarket"] | None = None
    sub_market_count: int | None = None
    market_id: str | None = None


class ConstituentSubMarket(BaseModel):
    condition_id: str | None = None
    clob_token_id: str | None = None
    price: float | None = None
    volume: float = 0.0


class BasketInfo(BaseModel):
    basket_name: str
    total_constituents: int
    index_price: float | None = None
    index_price_scaled: float | None = None
    computed_at: datetime | None = None
    status: str = "active"
    is_tradeable: bool = True
    # DB registry fields (PLAN.md): present when the baskets table has a row.
    slug: str | None = None
    expiry_at: datetime | None = None
    onchain_index_id: str | None = None


class BasketDetail(BasketInfo):
    constituents: list[ConstituentMarket] = []
    markets_filtered_out: int = 0
    excluded_markets: list[dict] = []


class PricePoint(BaseModel):
    ts: datetime
    basket_name: str
    index_price: float | None = None
    scaled_price: float | None = None
    constituent_count: int | None = None


class BasketPriceResponse(BaseModel):
    basket_name: str
    index_price: float | None = None
    scaled_price: float | None = None
    computed_at: datetime | None = None
    constituent_count: int | None = None
    status: str = "active"
    is_tradeable: bool = True
    slug: str | None = None
    expiry_at: datetime | None = None
    onchain_index_id: str | None = None


class BasketPriceResponseWithChange(BasketPriceResponse):
    change_24h_abs: float | None = None
    change_24h_pct: float | None = None


class BasketHistoryResponse(BaseModel):
    basket_name: str
    prices: list[PricePoint] = []


class BasketListResponse(BaseModel):
    baskets: list[BasketInfo] = []


# Candles
class Candle(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float


class CandlesResponse(BaseModel):
    basket_name: str
    interval: str
    candles: list[Candle] = []


# ── DB-backed basket registry (PLAN.md: baskets table) ──────────────
# Stored columns are theme / market_count / window+expiry; `name` is a
# generated display label (see xleuth_shared.baskets.generate_name).

class BasketRecord(BaseModel):
    id: int | None = None
    slug: str
    name: str
    theme: str
    market_count: int
    window_start: datetime
    expiry_at: datetime
    settlement_at: datetime | None = None
    selection_rules: dict = {}
    status: str = "draft"
    onchain_index_id: str | None = None
    register_tx_hash: str | None = None
    registered_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: str | None = None


class BasketCreate(BaseModel):
    theme: str
    market_count: int
    window_start: datetime
    expiry_at: datetime
    selection_rules: dict = {}
    created_by: str | None = None


class BasketEvent(BaseModel):
    basket_id: int
    event: str
    actor: str | None = None
    payload: dict = {}
    created_at: datetime | None = None
