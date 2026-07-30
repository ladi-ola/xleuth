from fastapi import APIRouter, Depends

from xleuth_api.db import Database
from xleuth_api.dependencies import get_current_user, get_db
from xleuth_shared.schemas.accounts import (
    TransactionHistoryResponse,
    TransactionInfo,
    UserInfo,
)

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("/me", response_model=UserInfo)
async def get_account(
    user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    fresh = await db.get_user(user["wallet_address"])
    if fresh is None:
        fresh = user
    return UserInfo(
        wallet_address=fresh["wallet_address"],
        alias=fresh.get("alias"),
        balance=fresh.get("balance", 0.0),
        realized_pnl=fresh.get("realized_pnl", 0.0),
        unrealized_pnl=fresh.get("unrealized_pnl", 0.0),
        created_at=fresh.get("created_at"),
    )


@router.put("/alias", response_model=UserInfo)
async def update_alias(
    alias: str,
    user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    updated = await db.update_user_alias(user["wallet_address"], alias)
    if updated is None:
        return UserInfo(wallet_address=user["wallet_address"])
    return UserInfo(
        wallet_address=updated["wallet_address"],
        alias=updated.get("alias"),
        balance=updated.get("balance", 0.0),
        realized_pnl=updated.get("realized_pnl", 0.0),
        unrealized_pnl=updated.get("unrealized_pnl", 0.0),
        created_at=updated.get("created_at"),
    )


@router.get("/transactions", response_model=TransactionHistoryResponse)
async def get_transactions(
    limit: int = 50,
    user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    txs = await db.get_transactions(user["wallet_address"], limit=limit)
    return TransactionHistoryResponse(
        wallet_address=user["wallet_address"],
        transactions=[
            TransactionInfo(
                id=t.get("id"),
                wallet_address=t["wallet_address"],
                tx_type=t["tx_type"],
                amount=t["amount"],
                tx_hash=t.get("tx_hash"),
                timestamp=t.get("timestamp"),
                related_position_id=t.get("related_position_id"),
            )
            for t in txs
        ],
    )
