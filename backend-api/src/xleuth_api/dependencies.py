from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from xleuth_api.auth.jwt import JWTHandler
from xleuth_api.db import Database

bearer_scheme = HTTPBearer(auto_error=False)


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_jwt_handler(request: Request) -> JWTHandler:
    return request.app.state.jwt_handler


def get_siwe_handler(request: Request) -> "SIWEHandler":
    return request.app.state.siwe_handler


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    jwt_handler: JWTHandler = Depends(get_jwt_handler),
    db: Database = Depends(get_db),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")
    wallet_address = jwt_handler.verify_token(credentials.credentials)
    if wallet_address is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = await db.get_user(wallet_address)
    if user is None:
        return {"wallet_address": wallet_address, "alias": None, "balance": 0.0, "realized_pnl": 0.0, "unrealized_pnl": 0.0, "created_at": None}
    return user
