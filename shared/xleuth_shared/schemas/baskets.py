from datetime import datetime
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


class BasketHistoryResponse(BaseModel):
    basket_name: str
    prices: list[PricePoint] = []


class BasketListResponse(BaseModel):
    baskets: list[BasketInfo] = []
