import re
from datetime import datetime, timezone
from typing import Any

from xleuth_ingestion.event_map import build_volume_map
from xleuth_ingestion.polymarket_client import PolymarketClient
from xleuth_ingestion.vwap import basket_vwap

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
    exclude_categories: str | None = None,
    markets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    parsed = parse_basket_name(basket_name)
    if not parsed:
        msg = f"Invalid basket name '{basket_name}'. Expected TOP<N>-<MONTH> (e.g. TOP50-JULY)"
        raise ValueError(msg)

    n, target_month, _ = parsed

    raw_markets = markets if markets is not None else await _fetch_all_markets(client)

    resolving = [m for m in raw_markets if market_resolves_in_month(m, target_month)]

    exclude_list = []
    if exclude_categories:
        exclude_list = [c.strip().lower() for c in exclude_categories.split(",")]

    excluded: list[dict[str, str]] = []
    filtered: list[dict[str, Any]] = []
    for m in resolving:
        category = PolymarketClient.get_category(m)
        if category and category.lower() in exclude_list:
            excluded.append({
                "id": str(m.get("id", "?")),
                "question": str(m.get("question", "")),
                "reason": f"category '{category}' is excluded (EXCLUDE_CATEGORIES={exclude_categories})",
            })
            continue
        filtered.append(m)

    filtered.sort(key=lambda m: PolymarketClient.get_volume(m), reverse=True)
    top_n = filtered[:n]

    volume_map = await build_volume_map(top_n, client)

    clob_token_map: dict[str, list[str]] = {}
    for m in top_n:
        cond_id = str(m.get("conditionId", ""))
        clob_token_map[cond_id] = PolymarketClient.get_clob_token_ids(m)

    all_token_ids = [tid for ids in clob_token_map.values() for tid in ids]
    midpoint_map = await client.get_midpoints_batch(all_token_ids)

    constituents: list[dict[str, Any]] = []
    constituent_prices: list[tuple[float, float]] = []

    for market in top_n:
        cond_id = str(market.get("conditionId", ""))
        event_id = str(PolymarketClient.get_event_id(market) or "")
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