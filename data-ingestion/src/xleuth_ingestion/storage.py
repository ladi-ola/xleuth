import json
import logging
from typing import Any

import asyncpg

logger = logging.getLogger("xleuth_ingestion.storage")

BASE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS index_prices (
    ts          TIMESTAMPTZ NOT NULL,
    basket_name TEXT NOT NULL,
    index_price DOUBLE PRECISION,
    scaled_price DOUBLE PRECISION,
    constituent_count INTEGER,
    constituents JSONB
);

CREATE TABLE IF NOT EXISTS market_prices (
    ts          TIMESTAMPTZ NOT NULL,
    market_id   TEXT NOT NULL,
    basket_name TEXT NOT NULL,
    question    TEXT,
    price       DOUBLE PRECISION,
    volume      DOUBLE PRECISION,
    event_id    TEXT
);
"""

HYPERTABLE_SQL = """
SELECT create_hypertable('index_prices', 'ts', if_not_exists => TRUE);
SELECT create_hypertable('market_prices', 'ts', if_not_exists => TRUE);
"""


class Storage:
    def __init__(self, dsn: str | None):
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None
        self._timescaledb = False

    async def connect(self) -> bool:
        if not self.dsn:
            logger.warning("No DATABASE_URL set; running in console-only mode (no persistence)")
            return False
        try:
            self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=5)
            return True
        except Exception:
            logger.warning("Database unavailable; running in console-only mode (no persistence)", exc_info=True)
            return False

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

    async def ensure_schema(self) -> None:
        if not self.pool:
            return
        async with self.pool.acquire() as conn:
            for statement in BASE_TABLE_SQL.split(";"):
                stmt = statement.strip()
                if stmt:
                    await conn.execute(stmt)

            self._timescaledb = await self._check_timescaledb(conn)
            if self._timescaledb:
                for statement in HYPERTABLE_SQL.split(";"):
                    stmt = statement.strip()
                    if stmt:
                        try:
                            await conn.execute(stmt)
                        except asyncpg.exceptions.DuplicateTableError:
                            pass
            else:
                logger.info("TimescaleDB not available; using plain tables")

    async def _check_timescaledb(self, conn) -> bool:
        try:
            row = await conn.fetchrow("SELECT extname FROM pg_extension WHERE extname = 'timescaledb'")
            return row is not None
        except Exception:
            return False

    async def save_basket(self, basket_result: dict[str, Any]) -> None:
        if not self.pool:
            return
        await self._save_index_price(basket_result)
        await self._save_market_prices(basket_result)

    async def cleanup_stale_baskets(self, active_baskets: list[str]) -> None:
        """Remove rows for unknown baskets only.

        Rows for dated baskets (e.g. TOP20-JULY) are never deleted: once an
        index resolves it must remain queryable as history. Only names that
        are neither in the active list nor valid dated basket names are purged.
        """
        if not self.pool or not active_baskets:
            return
        async with self.pool.acquire() as conn:
            for table in ("index_prices", "market_prices"):
                result = await conn.execute(
                    "DELETE FROM {} "
                    "WHERE basket_name != ALL($1::text[]) "
                    "AND basket_name !~ '^[A-Z]+[0-9]+-[A-Z]+(-[0-9]{4})?$'".format(table),
                    active_baskets,
                )
                logger.info("Cleaned up stale rows from %s (active=%s)", table, active_baskets)

    async def _save_index_price(self, basket_result: dict[str, Any]) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM index_prices WHERE basket_name = $1",
                    basket_result["basket_name"],
                )
                await conn.execute(
                    """
                    INSERT INTO index_prices (ts, basket_name, index_price, scaled_price, constituent_count, constituents)
                    VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                    """,
                    basket_result["computed_at"],
                    basket_result["basket_name"],
                    basket_result["index_price"],
                    basket_result["index_price_scaled"],
                    basket_result["total_constituents"],
                    json.dumps(basket_result["constituents"]),
                )

    async def _save_market_prices(self, basket_result: dict[str, Any]) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM market_prices WHERE basket_name = $1",
                    basket_result["basket_name"],
                )
                for c in basket_result["constituents"]:
                    await conn.execute(
                        """
                        INSERT INTO market_prices (ts, market_id, basket_name, question, price, volume, event_id)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        """,
                        basket_result["computed_at"],
                        str(c.get("market_id", "")),
                        basket_result["basket_name"],
                        c.get("question"),
                        c.get("price"),
                        c.get("volume"),
                        c.get("event_id"),
                    )
