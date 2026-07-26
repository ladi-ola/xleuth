from collections import defaultdict
from typing import Any

from xleuth_ingestion.polymarket_client import PolymarketClient


async def build_volume_map(
    markets: list[dict[str, Any]],
    client: PolymarketClient,
) -> dict[str, float]:
    """Map each filtered market's conditionId → live volume from Data API.

    Dedup by event ID first so /live-volume is called once per unique event,
    then match each constituent back by condition ID.
    """
    if not markets:
        return {}

    event_to_conditions: dict[str, list[str]] = defaultdict(list)
    for m in markets:
        events = m.get("events", [])
        if events:
            event_id = str(events[0].get("id", ""))
            cond_id = str(m.get("conditionId", ""))
            if event_id and cond_id:
                event_to_conditions[event_id].append(cond_id)

    volume_map: dict[str, float] = {}
    for event_id, cond_ids in event_to_conditions.items():
        try:
            vol_data = await client.get_live_volume(int(event_id))
        except (ValueError, TypeError):
            continue
        if vol_data is None:
            continue
        markets_vol = vol_data.get("markets", [])
        for entry in markets_vol:
            raw_market = entry.get("market", "")
            value = float(entry.get("value", 0) or 0)
            normalized = raw_market.lower()
            for cond_id in cond_ids:
                if cond_id.lower() == normalized:
                    volume_map[cond_id] = volume_map.get(cond_id, 0) + value

    return volume_map