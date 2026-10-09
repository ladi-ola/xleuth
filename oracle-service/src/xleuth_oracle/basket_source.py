"""DB-first basket discovery for the oracle pusher (short TTL cache).

PLAN.md: price_reader/pusher only handle ACTIVE baskets that have an
onchain_index_id; stop pushing after expiry. A newly activated basket is
picked up without a restart (TTL expiry, not process restart).

Transition: env-template names (legacy keccak(NAME) ids) fill the gap until
the backfill migration lands, so live pushes never stop.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

logger = logging.getLogger("xleuth_oracle.basket_source")

_TTL_S = int(os.getenv("ORACLE_BASKET_CACHE_TTL_S", "60"))

_cache: dict = {"at": 0.0, "items": []}


def _legacy_id(name: str) -> str:
    from eth_utils import keccak

    return "0x" + keccak(text=name).hex()


async def discover_baskets(config, pool=None, now: datetime | None = None,
                           force: bool = False) -> list[dict]:
    """Return [{name, index_id, expiry, source}]. Cached for _TTL_S."""
    now = now or datetime.now(timezone.utc)
    if not force and _cache["items"] and (time.time() - _cache["at"]) < _TTL_S:
        return _cache["items"]

    items: list[dict] = []
    seen: set[str] = set()
    if pool is not None:
        try:
            from xleuth_shared.db_baskets import list_active

            for row in await list_active(pool, now=now):
                idx = row.get("onchain_index_id")
                if not idx:
                    continue  # PLAN: only baskets WITH an on-chain id
                items.append({"name": row["name"], "index_id": idx,
                              "expiry": row["expiry_at"], "source": "db"})
                seen.add(row["name"])
        except Exception:
            logger.warning("DB basket discovery failed; env fallback", exc_info=True)

    for name in (config.baskets or []):
        if name in seen:
            continue
        items.append({"name": name, "index_id": _legacy_id(name),
                      "expiry": None, "source": "env"})
        seen.add(name)

    _cache.update(at=time.time(), items=items)
    return items


def clear_cache() -> None:
    _cache.update(at=0.0, items=[])
