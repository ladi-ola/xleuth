from pydantic import BaseModel


class NonceResponse(BaseModel):
    nonce: str
    wallet_address: str
    message: str


class LoginRequest(BaseModel):
    wallet_address: str
    signature: str
    message: str
    nonce: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in_minutes: int


class SIWEMessage(BaseModel):
    domain: str
    address: str
    statement: str | None = None
    uri: str
    version: str = "1"
    chain_id: int
    nonce: str
    issued_at: str
    expiration_time: str | None = None
