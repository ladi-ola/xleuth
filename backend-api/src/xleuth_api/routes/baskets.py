from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query

from xleuth_api.db import Database
from xleuth_api.dependencies import get_db
from xleuth_shared.basket_lifecycle import basket_status, is_tradeable
from xleuth_shared.schemas.baskets import (
    BasketDetail,
    BasketHistoryResponse,
    BasketInfo,
    BasketListResponse,
    BasketPriceResponse,
    BasketPriceResponseWithChange,
    CandlesResponse,
    Candle,
    ConstituentMarket,
    PricePoint,
)

router = APIRouter(prefix="/baskets", tags=["baskets"])


def _lifecycle(basket_name: str) -> tuple[str, bool]:
    now = datetime.now(timezone.utc)
    return basket_status(basket_name, now), is_tradeable(basket_name, now)


async def _add_24h_change(db: Database, basket_name: str, response: BasketPriceResponse) -> BasketPriceResponseWithChange:
    """Add 24h change fields to a basket price response."""
    price_24h_ago = await db.get_price_24h_ago(basket_name)
    current_price = response.scaled_price
    
    change_24h_abs = None
    change_24h_pct = None
    
    if current_price is not None and price_24h_ago is not None and price_24h_ago > 0:
        change_24h_abs = current_price - price_24h_ago
        change_24h_pct = (change_24h_abs / price_24h_ago) * 100
    
    return BasketPriceResponseWithChange(
        basket_name=response.basket_name,
        index_price=response.index_price,
        scaled_price=response.scaled_price,
        computed_at=response.computed_at,
        constituent_count=response.constituent_count,
        status=response.status,
        is_tradeable=response.is_tradeable,
        change_24h_abs=change_24h_abs,
        change_24h_pct=change_24h_pct,
    )


@router.get("", response_model=BasketListResponse)
async def list_baskets(
    db: Database = Depends(get_db),
):
    rows = await db.list_baskets()
    baskets = []
    for r in rows:
        status, tradeable = _lifecycle(r["basket_name"])
        # Create base response
        base = BasketInfo(
            basket_name=r["basket_name"],
            total_constituents=r.get("constituent_count") or 0,
            index_price=r.get("index_price"),
            index_price_scaled=r.get("scaled_price"),
            computed_at=r.get("ts"),
            status=status,
            is_tradeable=tradeable,
        )
        # Add 24h change
        price_24h_ago = await db.get_price_24h_ago(r["basket_name"])
        current_price = r.get("scaled_price")
        
        change_24h_abs = None
        change_24h_pct = None
        
        if current_price is not None and price_24h_ago is not None and price_24h_ago > 0:
            change_24h_abs = current_price - price_24h_ago
            change_24h_pct = (change_24h_abs / price_24h_ago) * 100
        
        baskets.append({
            "basket_name": base.basket_name,
            "total_constituents": base.total_constituents,
            "index_price": base.index_price,
            "index_price_scaled": base.index_price_scaled,
            "computed_at": base.computed_at,
            "status": base.status,
            "is_tradeable": base.is_tradeable,
            "change_24h_abs": change_24h_abs,
            "change_24h_pct": change_24h_pct,
        })
    return BasketListResponse(baskets=baskets)


@router.get("/{basket_name}/price", response_model=BasketPriceResponseWithChange)
async def get_basket_price(
    basket_name: str,
    db: Database = Depends(get_db),
):
    row = await db.get_latest_basket_price(basket_name)
    status, tradeable = _lifecycle(basket_name)
    if row is None:
        base = BasketPriceResponse(
            basket_name=basket_name, status=status, is_tradeable=tradeable
        )
        return await _add_24h_change(db, basket_name, base)
    base = BasketPriceResponse(
        basket_name=row["basket_name"],
        index_price=row.get("index_price"),
        scaled_price=row.get("scaled_price"),
        computed_at=row.get("ts"),
        constituent_count=row.get("constituent_count"),
        status=status,
        is_tradeable=tradeable,
    )
    return await _add_24h_change(db, basket_name, base)


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
            condition_id=r.get("condition_id"),
            clob_token_id=r.get("clob_token_id"),
            event_id=r.get("event_id"),
            question=r.get("question"),
            end_date=r.get("end_date"),
            price=r.get("price"),
            volume=r.get("volume", 0.0),
            price_source=r.get("price_source"),
            market_id=r.get("market_id"),
        )
        for r in constituents_raw
    ]
    latest = await db.get_latest_basket_price(basket_name)
    status, tradeable = _lifecycle(basket_name)
    return BasketDetail(
        basket_name=basket_name,
        total_constituents=len(constituents),
        index_price=latest.get("index_price") if latest else None,
        index_price_scaled=latest.get("scaled_price") if latest else None,
        computed_at=latest.get("ts") if latest else None,
        status=status,
        is_tradeable=tradeable,
        constituents=constituents,
    )


@router.get("/{basket_name}/candles", response_model=CandlesResponse)
async def get_candles(
    basket_name: str,
    interval: str = Query("15m", description="Candle interval (1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w)"),
    limit: int = Query(200, le=10000),
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    db: Database = Depends(get_db),
):
    """Get OHLC candles for a basket using TimescaleDB time_bucket."""
    rows = await db.get_candles(basket_name, interval, limit, start, end)
    candles = [
        Candle(
            time=int(r["bucket"].timestamp()) if hasattr(r["bucket"], 'timestamp') else int(r["bucket"]),
            open=r["open"],
            high=r["high"],
            low=r["low"],
            close=r["close"],
        )
        for r in rows
    ]
    return CandlesResponse(
        basket_name=basket_name,
        interval=interval,
        candles=candles,
    )
