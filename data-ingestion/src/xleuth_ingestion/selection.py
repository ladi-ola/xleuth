"""Pure constituent selection: ONE implementation shared by poller + CLI dry-run.

PLAN.md: "Refactor selection logic out of basket_builder.py into a pure
function shared by the poller and the CLI dry-run so there is one
implementation."

Pure = no I/O, no Polymarket client, no name parsing. Inputs are explicit
(market_count, target_month, exclude_categories). The basket NAME is never
parsed here; callers derive month/count from DB columns (or legacy
parse_basket_name only in the deprecated wrapper).
"""

from __future__ import annotations

from typing import Any

from xleuth_ingestion.polymarket_client import PolymarketClient


def select_constituents(
    markets: list[dict[str, Any]],
    *,
    market_count: int,
    target_month: int | None,
    exclude_categories: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Filter by resolve-month + category, sort by volume desc, take top-N.

    Returns (top_n, excluded). Deterministic, side-effect free.
    target_month=None means no month filter (custom non-monthly indexes).
    """
    if market_count <= 0:
        raise ValueError(f"market_count must be > 0, got {market_count!r}")

    from xleuth_ingestion.basket_builder import market_resolves_in_month

    if target_month is None:
        resolving = list(markets)
    else:
        resolving = [m for m in markets if market_resolves_in_month(m, target_month)]

    exclude_list = []
    if exclude_categories:
        exclude_list = [c.strip().lower() for c in exclude_categories.split(",") if c.strip()]

    excluded: list[dict[str, str]] = []
    filtered: list[dict[str, Any]] = []
    for m in resolving:
        category = PolymarketClient.get_category(m)
        if category and category.lower() in exclude_list:
            excluded.append({
                "id": str(m.get("id", "?")),
                "question": str(m.get("question", "")),
                "reason": f"category '{category}' is excluded",
            })
            continue
        filtered.append(m)

    filtered.sort(key=lambda m: PolymarketClient.get_volume(m), reverse=True)
    return filtered[:market_count], excluded


def resolve_target_month(expiry_month: int | None, selection_rules: dict | None) -> int | None:
    """Custom indexes may override the month filter via selection_rules.

    selection_rules={"target_month": 10} forces October regardless of expiry.
    selection_rules={"target_month": null} disables month filtering (all markets).
    Default: the expiry month (monthly baskets).
    """
    if selection_rules and "target_month" in selection_rules:
        tm = selection_rules["target_month"]
        if tm is None:
            return None
        tm = int(tm)
        if not 1 <= tm <= 12:
            raise ValueError(f"selection_rules.target_month must be 1-12, got {tm!r}")
        return tm
    return expiry_month
