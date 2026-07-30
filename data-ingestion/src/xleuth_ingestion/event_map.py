import logging
from collections import defaultdict
from typing import Any

import httpx

logger = logging.getLogger("xleuth_ingestion.event_map")


def _normalize_id(raw: str) -> str:
    """Strip 0x prefix and lowercase for comparison."""
    return raw.removeprefix("0x").removeprefix("0X").lower()


async def build_volume_map(
    markets: list[dict[str, Any]],
    client: "PolymarketClient",
) -> dict[str, float]:
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
        except httpx.HTTPError:
            logger.warning("HTTP error fetching live volume for event %s; skipping", event_id)
            continue
        except Exception:
            logger.warning("Unexpected error fetching live volume for event %s; skipping", event_id)
            continue
        if vol_data is None:
            continue
        markets_vol = vol_data.get("markets", [])
        for entry in markets_vol:
            raw_market = entry.get("market", "")
            value = float(entry.get("value", 0) or 0)
            normalized_key = _normalize_id(raw_market)
            matched = False
            for cond_id in cond_ids:
                if _normalize_id(cond_id) == normalized_key:
                    volume_map[cond_id] = volume_map.get(cond_id, 0) + value
                    matched = True
                    break
            if not matched:
                logger.debug(
                    "No condition ID matched for market %s in event %s; cond_ids=%s",
                    raw_market, event_id, cond_ids,
                )

    return volume_map