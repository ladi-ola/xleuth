import re

from fastapi import APIRouter, Depends, HTTPException, Request

from xleuth_api.chain import ChainStateReader
from xleuth_api.db import Database
from xleuth_api.dependencies import get_current_user, get_db
from xleuth_shared.schemas.accounts import (
    TransactionHistoryResponse,
    TransactionInfo,
    UserInfo,
)
from xleuth_shared.schemas.orders import PortfolioSummaryResponse

router = APIRouter(prefix="/accounts", tags=["accounts"])


def get_chain_reader(request: Request) -> ChainStateReader | None:
    return request.app.state.chain_reader


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
    # Task 15: server-side alias validation (real enforcement; the UI has no
    # alias input today but the endpoint is reachable). React escapes on
    # render, but we still bound length/charset at the boundary.
    clean = (alias or "").strip()
    if not clean or len(clean) > 32:
        raise HTTPException(status_code=422, detail="alias must be 1-32 characters")
    if not re.fullmatch(r"[A-Za-z0-9 _.\-]+", clean):
        raise HTTPException(status_code=422, detail="alias holds invalid characters")
    updated = await db.update_user_alias(user["wallet_address"], clean)
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


@router.get("/summary", response_model=PortfolioSummaryResponse)
async def get_summary(
    user: dict = Depends(get_current_user),
    chain: ChainStateReader | None = Depends(get_chain_reader),
):
    """Get portfolio summary with margin breakdown.

    free_margin / vault_free = free (unlocked) collateral inside the
        CollateralVault. This is the only balance the matching engine counts
        as order margin.
    wallet_balance = test-USDC held in the user's own wallet. Faucet claims
        land here; it becomes tradeable only after an approve + vault.deposit.
    used_margin = margin locked by open positions + margin reserved for resting orders
    total_balance = free_margin + wallet_balance + used_margin
    SL/TP orders carry no separate reservation
    """
    if chain is None:
        # Return zeros if chain reader not available
        return PortfolioSummaryResponse(
            total_balance=0.0,
            free_margin=0.0,
            used_margin=0.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
        )
    
    wallet = user["wallet_address"]
    
    # Vault balance is the only tradeable margin. Wallet collateral is shown
    # separately so a faucet claim is visible immediately without pretending
    # it is already usable by the matching engine.
    vault_balance = chain.free_balance(wallet) / 1e6
    read_wallet_balance = getattr(chain, "wallet_balance", None)
    wallet_balance = read_wallet_balance(wallet) / 1e6 if callable(read_wallet_balance) else 0.0
    total_balance = vault_balance + wallet_balance
    
    # Get all positions to calculate used margin and unrealized PnL
    used_margin = 0.0
    unrealized_pnl = 0.0
    
    # We need to know which baskets the user has positions in
    # For now, we'll check the baskets from the matching engine config
    # In a real implementation, we'd query PositionManager for all baskets
    # This is a simplified version - in production, we'd need to track all active baskets
    
    # For now, return basic summary with free balance
    # A full implementation would iterate through all baskets and sum up positions
    return PortfolioSummaryResponse(
        total_balance=total_balance,
        free_margin=vault_balance,
        used_margin=used_margin,
        unrealized_pnl=unrealized_pnl,
        realized_pnl=0.0,  # Would need transaction history to compute
        vault_free=vault_balance,
        wallet_balance=wallet_balance,
    )
