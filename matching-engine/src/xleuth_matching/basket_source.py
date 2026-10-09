"""DB-first basket registry for the matching engine (short TTL cache).

PLAN.md: config.py and margin_check read per-basket params and the basket's
on-chain ID from the DB; reject orders on non-active baskets. Newly
activated baskets are picked up without a redeploy (books created on demand).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

logger = logging.getLogger("xleuth_matching.basket_source")

_TTL_S = int(os.getenv("ENGINE_BASKET_CACHE_TTL_S", "60"))

_cache: dict = {"at": 0.0, "rows": []}


def _legacy_id(name: str) -> str:
    from eth_utils import keccak

    return "0x" + keccak(text=name).hex()


async def get_active_rows(pool=None, now: datetime | None = None,
                          force: bool = False) -> list[dict]:
    """DB active rows (with onchain_index_id) or [] — never raises."""
    now = now or datetime.now(timezone.utc)
    if not force and _cache["rows"] and (time.time() - _cache["at"]) < _TTL_S:
        return _cache["rows"]
    rows: list[dict] = []
    if pool is not None:
        try:
            from xleuth_shared.db_baskets import list_active

            rows = await list_active(pool, now=now)
        except Exception:
            logger.warning("DB basket fetch failed; env fallback", exc_info=True)
    _cache.update(at=time.time(), rows=rows)
    return rows


def index_ids_from_rows(rows: list[dict]) -> dict[str, str]:
    return {r["name"]: r["onchain_index_id"] for r in rows if r.get("onchain_index_id")}


def clear_cache() -> None:
    _cache.update(at=0.0, rows=[])
