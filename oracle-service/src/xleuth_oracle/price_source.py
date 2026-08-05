"""Reads live basket index prices from data-ingestion.

Primary source is the Postgres `index_prices` table (the scaled_price column,
in 0-100 points, exactly what on-chain prices use). Optional Redis stream
fallback reads the `xleuth:basket:{name}:price` channel published by
data-ingestion's poller. Both are "stored or streamed" values, never fresh
Gamma computations done by the service itself.

A None price means "no data yet for this basket" — the caller skips the push
for that cycle rather than signing a garbage price.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("xleuth_oracle.price_source")


class PostgresPriceSource:
    def __init__(self, dsn: str | None):
        self.dsn = dsn
        self._pool = None

    async def connect(self) -> bool:
        if not self.dsn:
            logger.warning("No DATABASE_URL; price source has no data")
            return False
        try:
            import asyncpg

            self._pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=2)
            logger.info("Connected to Postgres price source")
            return True
        except Exception:
            logger.warning("Postgres unavailable for prices", exc_info=True)
            return False

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    async def scaled_price(self, basket_name: str) -> float | None:
        if not self._pool:
            return None
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT scaled_price FROM index_prices "
                    "WHERE basket_name = $1 ORDER BY ts DESC LIMIT 1",
                    basket_name,
                )
        except Exception:
            logger.warning("DB price read failed for %s", basket_name, exc_info=True)
            return None
        if row is None:
            return None
        return float(row["scaled_price"])


class RedisPriceSource:
    """Reads the poller's live channel. Kept separate so DB and stream I/O are
    each independently testable/failable."""

    def __init__(self, redis_url: str | None):
        self.redis_url = redis_url
        self._client = None

    async def connect(self) -> bool:
        if not self.redis_url:
            return False
        try:
            import redis.asyncio as aioredis

            self._client = aioredis.from_url(self.redis_url, decode_responses=True)
            await self._client.ping()
            logger.info("Connected to Redis price stream at %s", self.redis_url)
            return True
        except Exception:
            logger.warning("Redis price stream unavailable", exc_info=True)
            self._client = None
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    async def scaled_price(self, basket_name: str) -> float | None:
        if not self._client:
            return None
        channel = f"xleuth:basket:{basket_name}:price"
        try:
            raw = await self._client.get(channel)
        except Exception:
            logger.warning("Redis read failed for %s", basket_name, exc_info=True)
            return None
        if not raw:
            return None
        try:
            payload = json.loads(raw)
            value = payload.get("scaled_price")
            return float(value) if value is not None else None
        except (ValueError, TypeError, json.JSONDecodeError):
            logger.warning("Bad payload on %s: %r", channel, raw)
            return None


class CompositePriceSource:
    """Tries Postgres first, then Redis stream, then None."""

    def __init__(self, sources: list[Any]):
        self.sources = sources

    async def connect(self) -> bool:
        ok = False
        for src in self.sources:
            if await src.connect():
                ok = True
        return ok

    async def close(self) -> None:
        for src in self.sources:
            await src.close()

    async def scaled_prices(self, baskets: list[str]) -> dict[str, float | None]:
        result: dict[str, float | None] = {}
        for name in baskets:
            value = None
            for src in self.sources:
                v = await src.scaled_price(name)
                if v is not None:
                    value = v
                    break
            result[name] = value
        return result