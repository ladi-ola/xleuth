import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from xleuth_ingestion.event_map import build_volume_map
from xleuth_ingestion.liquidity_filter import filter_markets
from xleuth_ingestion.polymarket_client import PolymarketClient
from xleuth_ingestion.vwap import basket_vwap, sub_outcome_vwap

MONTH_NAMES = {
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4,
    "MAY": 5, "JUNE": 6, "JULY": 7, "AUGUST": 8,
    "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4,
    "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8,
    "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

BASKET_PATTERN = re.compile(r"^TOP(\d+)-([A-Z]+)$")


def parse_basket_name(name: str) -> tuple[int, int, str] | None:
    m = BASKET_PATTERN.match(name.upper())
    if not m:
        return None
    n = int(m.group(1))
    month_str = m.group(2)
    month_num = MONTH_NAMES.get(month_str)
    if month_num is None:
        return None
    return n, month_num, name


def market_resolves_in_month(market: dict[str, Any], target_month: int) -> bool:
    end_date = market.get("endDate") or market.get("endDateIso")
    if not end_date:
        return False
    try:
        dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        return dt.month == target_month
    except (ValueError, TypeError):
        return False


def group_markets_by_event(markets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in markets:
        events = m.get("events", [])
        if events:
            event_id = str(events[0].get("id", ""))
            groups[event_id].append(m)
        else:
            groups[f"standalone_{m.get('id')}"].append(m)
    return groups


async def _fetch_all_markets(
    client: PolymarketClient,
    limit_per_page: int = 100,
    max_pages: int = 100,
) -> list[dict[str, Any]]:
    all_markets: list[dict[str, Any]] = []
    for page in range(max_pages):
        try:
            batch = await client.get_markets(
                limit=limit_per_page,
                offset=page * limit_per_page,
                order_by="volumeNum",
                ascending=False,
                closed=False,
                active=True,
            )
        except Exception:
            break
        if not batch:
            break
        all_markets.extend(batch)
        if len(batch) < limit_per_page:
            break
    return all_markets


def _resolve_price(
    market: dict[str, Any],
    midpoint_map: dict[str, float],
    clob_token_map: dict[str, list[str]],
    cond_id: str,
) -> tuple[float | None, str, str | None]:
    token_ids = clob_token_map.get(cond_id, [])
    yes_token = token_ids[0] if len(token_ids) >= 1 else None
    price = midpoint_map.get(yes_token) if yes_token else None
    if price is None and token_ids:
        for tid in token_ids:
            p = midpoint_map.get(tid)
            if p is not None:
                price = p
                yes_token = tid
                break
    source = "clob"
    if price is None:
        fallback = PolymarketClient.parse_outcome_prices(market)
        price = fallback[0] if fallback else None
        source = "gamma_fallback"
    return price, source, yes_token


async def build_basket(
    basket_name: str,
    client: PolymarketClient,
    min_volume_usd: float,
    min_liquidity_score: float,
    exclude_categories: str | None = None,
    liquidity_reference_usd: float = 100_000.0,
    oi_reference_usd: float = 500_000.0,
) -> dict[str, Any]:
    parsed = parse_basket_name(basket_name)
    if not parsed:
        msg = f"Invalid basket name '{basket_name}'. Expected TOP<N>-<MONTH> (e.g. TOP50-JULY)"
        raise ValueError(msg)

    n, target_month, _ = parsed

    raw_markets = await _fetch_all_markets(client)

    resolving = [m for m in raw_markets if market_resolves_in_month(m, target_month)]

    filtered, excluded = filter_markets(
        resolving,
        min_volume_usd=min_volume_usd,
        min_liquidity_score=min_liquidity_score,
        exclude_categories=exclude_categories,
        liquidity_reference_usd=liquidity_reference_usd,
        oi_reference_usd=oi_reference_usd,
    )

    filtered.sort(key=lambda m: PolymarketClient.get_volume(m), reverse=True)
    top_n = filtered[:n]

    volume_map = await build_volume_map(top_n, client)

    clob_token_map: dict[str, list[str]] = {}
    for m in top_n:
        cond_id = str(m.get("conditionId", ""))
        clob_token_map[cond_id] = PolymarketClient.get_clob_token_ids(m)

    all_token_ids = [tid for ids in clob_token_map.values() for tid in ids]
    midpoint_map = await client.get_midpoints_batch(all_token_ids)

    event_groups = group_markets_by_event(top_n)

    constituents: list[dict[str, Any]] = []
    constituent_prices: list[tuple[float, float]] = []

    for event_id, group in event_groups.items():
        if len(group) == 1:
            market = group[0]
            cond_id = str(market.get("conditionId", ""))
            price, source, yes_token = _resolve_price(market, midpoint_map, clob_token_map, cond_id)
            volume = volume_map.get(cond_id, PolymarketClient.get_volume(market))

            constituents.append({
                "condition_id": cond_id,
                "clob_token_id": yes_token,
                "event_id": event_id,
                "question": market.get("question"),
                "end_date": market.get("endDate") or market.get("endDateIso"),
                "price": price,
                "volume": volume,
                "price_source": source,
            })
            if price is not None:
                constituent_prices.append((price, volume))
        else:
            group_prices_volumes: list[tuple[float, float]] = []
            sub_constituents: list[dict[str, Any]] = []
            for market in group:
                cond_id = str(market.get("conditionId", ""))
                price, source, yes_token = _resolve_price(market, midpoint_map, clob_token_map, cond_id)
                volume = volume_map.get(cond_id, PolymarketClient.get_volume(market))

                sub_constituents.append({
                    "condition_id": cond_id,
                    "clob_token_id": yes_token,
                    "price": price,
                    "volume": volume,
                })
                if price is not None:
                    group_prices_volumes.append((price, volume))

            vwap_price = sub_outcome_vwap(group_prices_volumes) if group_prices_volumes else None
            total_volume = sum(v for _, v in group_prices_volumes)

            constituents.append({
                "market_id": event_id,
                "question": group[0].get("events", [{}])[0].get("title", "multi-outcome event"),
                "price": vwap_price,
                "volume": total_volume,
                "event_id": event_id,
                "end_date": group[0].get("endDate") or group[0].get("endDateIso"),
                "sub_markets": sub_constituents,
                "sub_market_count": len(sub_constituents),
            })
            if vwap_price is not None:
                constituent_prices.append((vwap_price, total_volume))

    index_price = basket_vwap(constituent_prices)

    return {
        "basket_name": basket_name,
        "computed_at": datetime.now(timezone.utc),
        "index_price": index_price,
        "index_price_scaled": round(index_price * 100, 2) if index_price is not None else None,
        "total_constituents": len(constituents),
        "markets_filtered_out": len(excluded),
        "excluded_markets": excluded,
        "constituents": constituents,
    }