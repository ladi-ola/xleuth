from fastapi import APIRouter, Depends, HTTPException, status

from xleuth_api.auth.dynamic_jwt import DynamicAuthHandler
from xleuth_api.db import Database
from xleuth_api.dependencies import get_current_user, get_db, get_dynamic_auth_handler
from xleuth_shared.schemas.auth import DynamicVerifyRequest, TokenResponse, UserInfo

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/verify", response_model=TokenResponse)
async def verify_dynamic_token(
    body: DynamicVerifyRequest,
    auth_handler: DynamicAuthHandler = Depends(get_dynamic_auth_handler),
    db: Database = Depends(get_db),
):
    try:
        wallet = auth_handler.verify_dynamic_token(body.token)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    normalized = wallet.lower()
    await db.upsert_user(normalized)
    token = auth_handler.issue_internal_token(normalized)
    return TokenResponse(
        access_token=token,
        expires_in_minutes=auth_handler.internal_expiry_minutes,
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