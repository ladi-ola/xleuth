from typing import Any


def compute_liquidity_score(
    market: dict[str, Any],
    liquidity_reference_usd: float = 100_000.0,
    oi_reference_usd: float = 500_000.0,
) -> float:
    from xleuth_ingestion.polymarket_client import PolymarketClient

    market_liquidity = PolymarketClient.get_liquidity(market)
    event_volume, event_oi = PolymarketClient.get_event_volume_and_oi(market)

    market_factor = min(1.0, market_liquidity / liquidity_reference_usd)
    oi_factor = min(1.0, event_oi / oi_reference_usd)

    score = (market_factor * 0.4) + (oi_factor * 0.6)
    return round(score, 4)


def filter_markets(
    markets: list[dict[str, Any]],
    min_volume_usd: float,
    min_liquidity_score: float,
    exclude_categories: str | None = None,
    liquidity_reference_usd: float = 100_000.0,
    oi_reference_usd: float = 500_000.0,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    excluded: list[dict[str, str]] = []
    passed: list[dict[str, Any]] = []

    exclude_list = []
    if exclude_categories:
        exclude_list = [c.strip().lower() for c in exclude_categories.split(",")]

    for market in markets:
        from xleuth_ingestion.polymarket_client import PolymarketClient

        volume = PolymarketClient.get_volume(market)

        # Volume check
        if volume < min_volume_usd:
            excluded.append({
                "id": str(market.get("id", "?")),
                "question": str(market.get("question", "")),
                "reason": f"volume ${volume:,.2f} < ${min_volume_usd:,.2f} MIN_MARKET_VOLUME_USD",
            })
            continue

        # Category check
        category = PolymarketClient.get_category(market)
        if category and category.lower() in exclude_list:
            excluded.append({
                "id": str(market.get("id", "?")),
                "question": str(market.get("question", "")),
                "reason": f"category '{category}' is excluded (EXCLUDE_CATEGORIES={exclude_categories})",
            })
            continue

        # Liquidity score check
        score = compute_liquidity_score(market, liquidity_reference_usd, oi_reference_usd)
        if score < min_liquidity_score:
            excluded.append({
                "id": str(market.get("id", "?")),
                "question": str(market.get("question", "")),
                "reason": (
                    f"liquidity_score {score:.4f} < {min_liquidity_score} "
                    f"MIN_MARKET_LIQUIDITY_SCORE"
                ),
            })
            continue

        passed.append(market)

    return passed, excluded
