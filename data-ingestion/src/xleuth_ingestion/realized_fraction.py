"""Realized basket fraction at expiry.

The index future settles to the volume-weighted realized YES fraction of its
constituents: each market resolves to YES (weight 1) or NO (weight 0), and the
basket's realized value is the average weighted by that market's trading volume.

CRITICAL: volumes MUST come from the event-deduped live-volume map built by
`build_volume_map` (one `/live-volume?id={eventId}` call per event). Using raw
per-market Gamma `volumeNum` instead would double-count when two basket
constituents share a parent event, inflating their weight in the realized
fraction — the same failure mode the resolution-quorum logic avoids.
"""

from typing import Any

from xleuth_ingestion.vwap import basket_vwap


def _outcome_yes_price(market: dict[str, Any]) -> float:
    """YES weight of a resolved market: 1.0 if YES won, 0.0 if NO won.

    Gamma exposes the final binary state via `outcomePrices`: after resolution
    it collapses to [1,0] (YES won) or [0,1] (NO won) for the standard two-
    outcome format. Any non-canonical state defaults to no vote (0.0) so it
    cannot inflate the index.
    """
    prices = market.get("outcomePrices")
    if isinstance(prices, str):
        import json

        try:
            prices = json.loads(prices)
        except json.JSONDecodeError:
            return 0.0
    if not isinstance(prices, list) or len(prices) < 2:
        return 0.0
    try:
        yes_price = float(prices[0])
        no_price = float(prices[1])
    except (TypeError, ValueError):
        return 0.0
    # A resolved binary market has exactly one outcome at 1 (within epsilon).
    if yes_price >= 1.0 - 1e-9 and no_price <= 1e-9:
        return 1.0
    if no_price >= 1.0 - 1e-9 and yes_price <= 1e-9:
        return 0.0
    return 0.0


def compute_realized_fraction(
    constituents: list[dict[str, Any]],
    volume_map: dict[str, float],
) -> float | None:
    """Volume-weighted realized YES fraction of a basket (0..1), or None if the
    basket has no tradeable volume.

    `volume_map` views must be the event-deduped live-volume map from
    `build_volume_map` (condition_id -> volume). We never fall back to raw
    per-market Gamma volume here — doing so defeats the per-event dedup.
    """
    pairs: list[tuple[float, float]] = []
    for market in constituents:
        cond_id = str(market.get("conditionId", ""))
        if not cond_id or cond_id not in volume_map:
            continue
        vol = float(volume_map[cond_id] or 0)
        if vol <= 0:
            continue
        yes_weight = _outcome_yes_price(market)
        pairs.append((yes_weight, vol))

    frac = basket_vwap(pairs)
    if frac is None:
        return None
    return frac