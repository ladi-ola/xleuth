from datetime import datetime, timezone
from typing import Any

from xleuth_ingestion.event_map import build_volume_map
from xleuth_ingestion.polymarket_client import PolymarketClient
from xleuth_ingestion.selection import resolve_target_month, select_constituents
from xleuth_ingestion.vwap import basket_vwap
from xleuth_shared.basket_lifecycle import MONTH_NAMES, parse_basket_name


def market_resolves_in_month(market: dict[str, Any], target_month: int) -> bool:
    end_date = market.get("endDate") or market.get("endDateIso")
    if not end_date:
        return False
    try:
        dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).month == target_month
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
    """Legacy wrapper: derives month/count by parsing the NAME.

    DEPRECATED — kept only so live template baskets keep working during the
    DB migration. New code must call build_basket_from_params() with explicit
    DB columns and never parse the name.
    """
    parsed = parse_basket_name(basket_name)
    if not parsed:
        msg = (
            f"Invalid basket name '{basket_name}'. "
            f"Expected <FAMILY><SIZE>-<MONTH> (e.g. TOP20-AUGUST)"
        )
        raise ValueError(msg)

    n, target_month, _ = parsed
    return await build_basket_from_params(
        basket_name=basket_name,
        client=client,
        market_count=n,
        target_month=target_month,
        exclude_categories=exclude_categories,
        markets=markets,
    )


async def build_basket_from_params(
    basket_name: str,
    client: PolymarketClient,
    *,
    market_count: int,
    target_month: int | None,
    exclude_categories: str | None = None,
    selection_rules: dict[str, Any] | None = None,
    markets: list[dict[str, Any]] | None = None,
    window_start: datetime | None = None,
    expiry_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a basket from explicit params (DB columns). Parses NO names."""
    if selection_rules:
        target_month = resolve_target_month(target_month, selection_rules)
        if selection_rules.get("exclude_categories"):
            exclude_categories = selection_rules["exclude_categories"]

    raw_markets = markets if markets is not None else await _fetch_all_markets(client)

    top_n, excluded = select_constituents(
        raw_markets,
        market_count=market_count,
        target_month=target_month,
        exclude_categories=exclude_categories,
        window_start=window_start,
        expiry_at=expiry_at,
    )

    volume_map = await build_volume_map(top_n, client)
    missing_volume = [str(m.get("conditionId", "")) for m in top_n
                      if str(m.get("conditionId", "")) not in volume_map]
    if missing_volume:
        raise ValueError(f"live_volume_unavailable: {len(missing_volume)} selected markets have no live taker volume")

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
        volume = volume_map[cond_id]

        constituents.append({
            "market_id": str(market.get("id") or market.get("conditionId", "")),
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
        "index_price_scaled": round(index_price * 100, 3) if index_price is not None else None,
        "total_constituents": len(constituents),
        "markets_filtered_out": len(excluded),
        "excluded_markets": excluded,
        "constituents": constituents,
    }
