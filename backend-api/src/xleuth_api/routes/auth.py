from fastapi import APIRouter, Depends, HTTPException, status

from xleuth_api.auth.jwt import JWTHandler
from xleuth_api.auth.siwe import SIWEHandler
from xleuth_api.db import Database
from xleuth_api.dependencies import get_current_user, get_db, get_jwt_handler, get_siwe_handler
from xleuth_shared.schemas.auth import LoginRequest, NonceResponse, TokenResponse
from xleuth_shared.schemas.accounts import UserInfo

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/nonce/{wallet_address}", response_model=NonceResponse)
async def get_nonce(
    wallet_address: str,
    siwe: SIWEHandler = Depends(get_siwe_handler),
):
    nonce = siwe.generate_nonce(wallet_address)
    message = siwe.build_message(wallet_address, nonce)
    return NonceResponse(nonce=nonce, wallet_address=wallet_address, message=message)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    siwe: SIWEHandler = Depends(get_siwe_handler),
    jwt_handler: JWTHandler = Depends(get_jwt_handler),
    db: Database = Depends(get_db),
):
    valid = siwe.verify_signature(
        wallet_address=body.wallet_address,
        signature=body.signature,
        message=body.message,
        nonce=body.nonce,
    )
    if not valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")
    normalized = body.wallet_address.lower()
    await db.upsert_user(normalized)
    token = jwt_handler.issue_token(normalized)
    return TokenResponse(
        access_token=token,
        expires_in_minutes=jwt_handler.expiry_minutes,
    )


@router.get("/me", response_model=UserInfo)
async def get_me(
    user: dict = Depends(get_current_user),
):
    return UserInfo(
        wallet_address=user["wallet_address"],
        alias=user.get("alias"),
        balance=user.get("balance", 0.0),
        realized_pnl=user.get("realized_pnl", 0.0),
        unrealized_pnl=user.get("unrealized_pnl", 0.0),
        created_at=user.get("created_at"),
    )
