from datetime import datetime
from pydantic import BaseModel


class UserInfo(BaseModel):
    wallet_address: str
    alias: str | None = None
    balance: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    created_at: datetime | None = None


class TransactionInfo(BaseModel):
    id: int | None = None
    wallet_address: str
    tx_type: str
    amount: float
    tx_hash: str | None = None
    timestamp: datetime | None = None
    related_position_id: int | None = None


class TransactionHistoryResponse(BaseModel):
    wallet_address: str
    transactions: list[TransactionInfo] = []
