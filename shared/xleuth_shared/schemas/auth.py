from pydantic import BaseModel


class DynamicVerifyRequest(BaseModel):
    token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in_minutes: int


class UserInfo(BaseModel):
    wallet_address: str
    alias: str | None = None
    balance: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    created_at: str | None = None