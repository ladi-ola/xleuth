from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from xleuth_api.auth.dynamic_jwt import DynamicAuthHandler
from xleuth_api.db import Database
from xleuth_shared.auth.internal_jwt import InternalJWTError

bearer_scheme = HTTPBearer(auto_error=False)


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_dynamic_auth_handler(request: Request) -> DynamicAuthHandler:
    return request.app.state.dynamic_auth_handler


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    auth_handler: DynamicAuthHandler = Depends(get_dynamic_auth_handler),
    db: Database = Depends(get_db),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token_missing")
    try:
        wallet_address = auth_handler.internal_verifier.verify_token(credentials.credentials)
    except InternalJWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=e.code)
    user = await db.get_user(wallet_address)
    if user is None:
        return {"wallet_address": wallet_address, "alias": None, "balance": 0.0, "realized_pnl": 0.0, "unrealized_pnl": 0.0, "created_at": None}
    return user