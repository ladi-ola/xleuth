from pydantic import BaseModel


class FaucetClaimRequest(BaseModel):
    smart_account_address: str


class FaucetClaimResponse(BaseModel):
    tx_hash: str
    status: str


class FaucetCooldownResponse(BaseModel):
    retry_after: int