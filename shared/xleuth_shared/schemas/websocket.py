from datetime import datetime
from pydantic import BaseModel


class WsPriceUpdate(BaseModel):
    type: str = "price_update"
    basket_name: str
    index_price: float | None = None
    scaled_price: float | None = None
    computed_at: datetime | None = None
    constituent_count: int | None = None


class WsSubscribeRequest(BaseModel):
    action: str
    basket_name: str
