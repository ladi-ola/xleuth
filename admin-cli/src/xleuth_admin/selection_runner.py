"""Dry-run: real selection logic vs live Polymarket data. Writes nothing."""

from __future__ import annotations

from datetime import datetime

from xleuth_ingestion.basket_builder import _fetch_all_markets, _resolve_price, market_resolves_in_month
from xleuth_ingestion.event_map import build_volume_map
from xleuth_ingestion.polymarket_client import PolymarketClient
from xleuth_ingestion.selection import resolve_target_month, select_constituents
from xleuth_ingestion.vwap import basket_vwap
from xleuth_shared.baskets import default_selection_rules


async def dry_run_report(*, market_count: int, expiry_at: datetime,
                         exclude_categories: str = "sports",
                         selection_rules: dict | None = None) -> dict:
    rules = selection_rules or default_selection_rules(exclude_categories)
    target_month = resolve_target_month(expiry_at.month, rules)
    client = PolymarketClient()
    try:
        all_markets = await _fetch_all_markets(client)
        top_n, excluded = select_constituents(
            all_markets, market_count=market_count, target_month=target_month,
            exclude_categories=rules.get("exclude_categories", exclude_categories),
        )
        volume_map = await build_volume_map(top_n, client)
        clob_token_map = {str(m.get("conditionId", "")): PolymarketClient.get_clob_token_ids(m)
                          for m in top_n}
        all_token_ids = [t for ids in clob_token_map.values() for t in ids]
        midpoint_map = await client.get_midpoints_batch(all_token_ids)

        constituents = []
        prices: list[tuple[float, float]] = []
        total_volume = 0.0
        for m in top_n:
            cond = str(m.get("conditionId", ""))
            price, source, _ = _resolve_price(m, midpoint_map, clob_token_map, cond)
            vol = volume_map.get(cond, PolymarketClient.get_volume(m))
            total_volume += vol or 0
            constituents.append({"question": m.get("question"), "price": price,
                                 "volume": vol, "price_source": source,
                                 "end_date": m.get("endDate") or m.get("endDateIso")})
            if price is not None:
                prices.append((price, vol))
        vwap = basket_vwap(prices)

        warnings = []
        if len(top_n) < market_count:
            warnings.append(f"too few liquid markets: {len(top_n)}/{market_count}")
        for m in top_n:
            end = m.get("endDate") or m.get("endDateIso")
            try:
                from datetime import datetime as _dt
                edt = _dt.fromisoformat(str(end).replace("Z", "+00:00"))
                if edt.replace(tzinfo=None) > expiry_at.replace(tzinfo=None):
                    warnings.append(f"market resolves after expiry: {m.get('question')}")
                    break
            except Exception:
                pass

        return {
            "actual_count": len(top_n), "requested_count": market_count,
            "total_volume": total_volume, "vwap_preview": vwap,
            "vwap_scaled_preview": round(vwap * 100, 2) if vwap is not None else None,
            "excluded_count": len(excluded),
            "constituents": constituents[:market_count],
            "warnings": warnings,
        }
    finally:
        await client.close()
