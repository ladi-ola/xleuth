from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from xleuth_api.db import Database
from xleuth_api.dependencies import get_db
from xleuth_shared.schemas.baskets import (
    BasketDetail,
    BasketHistoryResponse,
    BasketInfo,
    BasketListResponse,
    BasketPriceResponse,
    ConstituentMarket,
    PricePoint,
)

router = APIRouter(prefix="/baskets", tags=["baskets"])


@router.get("", response_model=BasketListResponse)
async def list_baskets(
    db: Database = Depends(get_db),
):
    rows = await db.list_baskets()
    baskets = [
        BasketInfo(
            basket_name=r["basket_name"],
            total_constituents=r.get("constituent_count") or 0,
            index_price=r.get("index_price"),
            index_price_scaled=r.get("scaled_price"),
            computed_at=r.get("ts"),
        )
        for r in rows
    ]
    return BasketListResponse(baskets=baskets)


@router.get("/{basket_name}/price", response_model=BasketPriceResponse)
async def get_basket_price(
    basket_name: str,
    db: Database = Depends(get_db),
):
    row = await db.get_latest_basket_price(basket_name)
    if row is None:
        return BasketPriceResponse(basket_name=basket_name)
    return BasketPriceResponse(
        basket_name=row["basket_name"],
        index_price=row.get("index_price"),
        scaled_price=row.get("scaled_price"),
        computed_at=row.get("ts"),
        constituent_count=row.get("constituent_count"),
    )


@router.get("/{basket_name}/history", response_model=BasketHistoryResponse)
async def get_basket_history(
    basket_name: str,
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    limit: int = Query(1000, le=10000),
    db: Database = Depends(get_db),
):
    rows = await db.get_basket_price_history(basket_name, start=start, end=end, limit=limit)
    prices = [
        PricePoint(
            ts=r["ts"],
            basket_name=r["basket_name"],
            index_price=r.get("index_price"),
            scaled_price=r.get("scaled_price"),
            constituent_count=r.get("constituent_count"),
        )
        for r in rows
    ]
    return BasketHistoryResponse(basket_name=basket_name, prices=prices)


@router.get("/{basket_name}/constituents", response_model=BasketDetail)
async def get_basket_constituents(
    basket_name: str,
    db: Database = Depends(get_db),
):
    constituents_raw = await db.get_basket_constituents(basket_name)
    constituents = [
        ConstituentMarket(
            market_id=r.get("market_id"),
            question=r.get("question"),
            price=r.get("price"),
            volume=r.get("volume", 0.0),
            event_id=r.get("event_id"),
        )
        for r in constituents_raw
    ]
    latest = await db.get_latest_basket_price(basket_name)
    return BasketDetail(
        basket_name=basket_name,
        total_constituents=len(constituents),
        index_price=latest.get("index_price") if latest else None,
        index_price_scaled=latest.get("scaled_price") if latest else None,
        computed_at=latest.get("ts") if latest else None,
        constituents=constituents,
    )
