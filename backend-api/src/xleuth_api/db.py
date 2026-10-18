import json
import logging
from datetime import datetime, timezone
from typing import Any

import asyncpg

logger = logging.getLogger("xleuth_api.db")

USER_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    wallet_address TEXT PRIMARY KEY,
    alias TEXT,
    balance DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    realized_pnl DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    unrealized_pnl DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    wallet_address TEXT NOT NULL REFERENCES users(wallet_address),
    tx_type TEXT NOT NULL,
    amount DOUBLE PRECISION NOT NULL,
    tx_hash TEXT,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    related_position_id INTEGER
);

CREATE INDEX IF NOT EXISTS idx_transactions_wallet ON transactions(wallet_address);

CREATE TABLE IF NOT EXISTS faucet_claims (
    wallet_address TEXT PRIMARY KEY,
    last_claim_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

# Price-history tables are written by data-ingestion, but the API must be able
# to create them itself so a fresh deploy (e.g. Render, no shell access) is
# self-healing. Plain PostgreSQL DDL — no TimescaleDB-only constructs.
PRICE_TABLE_SQL = """
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

CREATE INDEX IF NOT EXISTS idx_index_prices_basket_ts
    ON index_prices (basket_name, ts DESC);
"""

# Candle interval -> bucket size in seconds. Whitelisted so the interval can
# never reach the SQL as an unsupported value.
CANDLE_INTERVAL_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
}


class Database:
    def __init__(self, dsn: str | None):
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> bool:
        if not self.dsn:
            logger.warning("No DATABASE_URL set; API will run without persistence")
            return False
        try:
            self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=5)
            return True
        except Exception:
            logger.warning("Database unavailable; API will run without persistence", exc_info=True)
            return False

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

    async def ensure_schema(self) -> None:
        if not self.pool:
            return
        async with self.pool.acquire() as conn:
            for statement in USER_TABLE_SQL.split(";"):
                stmt = statement.strip()
                if stmt:
                    await conn.execute(stmt)
            # Price history tables (idempotent): created here too so the API
            # works on a fresh deploy even before data-ingestion runs.
            for statement in PRICE_TABLE_SQL.split(";"):
                stmt = statement.strip()
                if stmt:
                    await conn.execute(stmt)
        # Baskets registry DDL (shared, idempotent). Reads below prefer the
        # baskets table and fall back to index_prices during migration.
        try:
            from xleuth_shared.db_baskets import ensure_baskets_schema

            await ensure_baskets_schema(self.pool)
        except Exception:
            logger.warning("baskets schema ensure failed", exc_info=True)

    async def get_basket_record(self, basket_name: str) -> dict | None:
        """Registry row by display name (or None pre-backfill)."""
        if not self.pool:
            return None
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM baskets WHERE name = $1", basket_name)
                if row is None:
                    return None
                d = dict(row)
                import json as _json

                if isinstance(d.get("selection_rules"), str):
                    d["selection_rules"] = _json.loads(d["selection_rules"])
                return d
        except Exception:
            return None

    async def list_basket_records(self) -> list[dict]:
        if not self.pool:
            return []
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("SELECT * FROM baskets ORDER BY expiry_at")
                out = []
                for r in rows:
                    d = dict(r)
                    import json as _json

                    if isinstance(d.get("selection_rules"), str):
                        d["selection_rules"] = _json.loads(d["selection_rules"])
                    out.append(d)
                return out
        except Exception:
            return []

    # ── Basket / Price reads (tables created by data-ingestion) ────────

    async def get_latest_basket_price(self, basket_name: str) -> dict | None:
        if not self.pool:
            return None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT ts, basket_name, index_price, scaled_price, constituent_count
                FROM index_prices
                WHERE basket_name = $1
                ORDER BY ts DESC
                LIMIT 1
                """,
                basket_name,
            )
            if row:
                return dict(row)
            return None

    async def get_basket_price_history(
        self, basket_name: str, start: datetime | None = None, end: datetime | None = None, limit: int = 1000
    ) -> list[dict]:
        if not self.pool:
            return []
        async with self.pool.acquire() as conn:
            if start and end:
                rows = await conn.fetch(
                    """
                    SELECT ts, basket_name, index_price, scaled_price, constituent_count
                    FROM index_prices
                    WHERE basket_name = $1 AND ts >= $2 AND ts <= $3
                    ORDER BY ts DESC
                    LIMIT $4
                    """,
                    basket_name,
                    start,
                    end,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT ts, basket_name, index_price, scaled_price, constituent_count
                    FROM index_prices
                    WHERE basket_name = $1
                    ORDER BY ts DESC
                    LIMIT $2
                    """,
                    basket_name,
                    limit,
                )
            return [dict(r) for r in rows]

    async def get_basket_constituents(self, basket_name: str) -> list[dict]:
        if not self.pool:
            return []
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT constituents
                FROM index_prices
                WHERE basket_name = $1
                ORDER BY ts DESC
                LIMIT 1
                """,
                basket_name,
            )
            if not row or not row["constituents"]:
                return []
            raw = row["constituents"]
            data = json.loads(raw) if isinstance(raw, str) else raw
            return [dict(c) for c in data]

    async def list_baskets(self) -> list[dict]:
        if not self.pool:
            return []
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (basket_name) basket_name, index_price, scaled_price, constituent_count, ts
                FROM index_prices
                ORDER BY basket_name, ts DESC
                """
            )
            return [dict(r) for r in rows]

    async def get_price_24h_ago(self, basket_name: str) -> float | None:
        """Get the scaled_price closest to 24 hours ago for 24h change calculation."""
        if not self.pool:
            return None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT scaled_price
                FROM index_prices
                WHERE basket_name = $1 AND ts <= NOW() - INTERVAL '24 hours'
                ORDER BY ts DESC
                LIMIT 1
                """,
                basket_name,
            )
            if row and row["scaled_price"] is not None:
                return float(row["scaled_price"])
            return None

    async def basket_exists(self, basket_name: str) -> bool:
        """True if the basket is known (registry row or any price history).

        Used to distinguish "known basket, no candles yet" (200 + empty list)
        from "unknown basket" (404).
        """
        if not self.pool:
            return False
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT
                        EXISTS(SELECT 1 FROM baskets WHERE name = $1) AS in_registry,
                        EXISTS(SELECT 1 FROM index_prices WHERE basket_name = $1) AS in_prices
                    """,
                    basket_name,
                )
        except Exception:
            return False
        if row is None:
            return False
        return bool(row["in_registry"] or row["in_prices"])

    async def get_candles(
        self, basket_name: str, interval: str, limit: int = 1000, start: datetime | None = None, end: datetime | None = None
    ) -> list[dict]:
        """OHLC candles using portable PostgreSQL bucketing.

        Buckets come from epoch math (``floor(epoch / step) * step``) so no
        TimescaleDB extension (``time_bucket``/``FIRST``/``LAST``) is needed —
        this runs on plain PostgreSQL. Returns the most recent ``limit``
        buckets in ascending time order. Raises ValueError for an unsupported
        interval (mapped to HTTP 400 by the route).
        """
        if not self.pool:
            return []
        step_seconds = CANDLE_INTERVAL_SECONDS.get(interval)
        if step_seconds is None:
            raise ValueError(f"Unsupported candle interval: {interval!r}")

        async with self.pool.acquire() as conn:
            params: list[Any] = [basket_name, step_seconds]
            query = """
                SELECT bucket, open, high, low, close
                FROM (
                    SELECT
                        to_timestamp(
                            floor(
                                extract(epoch FROM ts)::double precision
                                / $2::double precision
                            ) * $2::double precision
                        ) AS bucket,
                        (array_agg(index_price ORDER BY ts ASC))[1] AS open,
                        MAX(index_price) AS high,
                        MIN(index_price) AS low,
                        (array_agg(index_price ORDER BY ts DESC))[1] AS close
                    FROM index_prices
                    WHERE basket_name = $1 AND index_price IS NOT NULL
            """
            if start:
                params.append(start)
                query += f" AND ts >= ${len(params)}"
            if end:
                params.append(end)
                query += f" AND ts <= ${len(params)}"
            params.append(limit)
            query += f"""
                    GROUP BY bucket
                    ORDER BY bucket DESC
                    LIMIT ${len(params)}
                ) AS recent_buckets
                ORDER BY bucket ASC
            """

            rows = await conn.fetch(query, *params)
            return [dict(r) for r in rows]

    # ── User / Transaction CRUD ────────────────────────────────────────

    async def upsert_user(self, wallet_address: str, alias: str | None = None) -> dict | None:
        if not self.pool:
            return None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO users (wallet_address, alias)
                VALUES ($1, $2)
                ON CONFLICT (wallet_address)
                DO UPDATE SET alias = COALESCE($2, users.alias)
                RETURNING wallet_address, alias, balance, realized_pnl, unrealized_pnl, created_at
                """,
                wallet_address,
                alias,
            )
            return dict(row) if row else None

    async def get_user(self, wallet_address: str) -> dict | None:
        if not self.pool:
            return None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT wallet_address, alias, balance, realized_pnl, unrealized_pnl, created_at FROM users WHERE wallet_address = $1",
                wallet_address,
            )
            return dict(row) if row else None

    async def update_user_alias(self, wallet_address: str, alias: str) -> dict | None:
        if not self.pool:
            return None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE users SET alias = $1 WHERE wallet_address = $2 RETURNING wallet_address, alias, balance, realized_pnl, unrealized_pnl, created_at",
                alias,
                wallet_address,
            )
            return dict(row) if row else None

    async def get_transactions(self, wallet_address: str, limit: int = 50) -> list[dict]:
        if not self.pool:
            return []
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, wallet_address, tx_type, amount, tx_hash, timestamp, related_position_id
                FROM transactions
                WHERE wallet_address = $1
                ORDER BY timestamp DESC
                LIMIT $2
                """,
                wallet_address,
                limit,
            )
            return [dict(r) for r in rows]

    async def add_transaction(
        self,
        wallet_address: str,
        tx_type: str,
        amount: float,
        tx_hash: str | None = None,
        related_position_id: int | None = None,
    ) -> dict | None:
        if not self.pool:
            return None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO transactions (wallet_address, tx_type, amount, tx_hash, related_position_id)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, wallet_address, tx_type, amount, tx_hash, timestamp, related_position_id
                """,
                wallet_address,
                tx_type,
                amount,
                tx_hash,
                related_position_id,
            )
            return dict(row) if row else None

    # ── Faucet ──────────────────────────────────────────────────────────

    async def get_last_faucet_claim(self, wallet_address: str) -> datetime | None:
        if not self.pool:
            return None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT last_claim_at FROM faucet_claims WHERE wallet_address = $1",
                wallet_address,
            )
            return row["last_claim_at"] if row else None

    async def record_faucet_claim(self, wallet_address: str) -> None:
        if not self.pool:
            return
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO faucet_claims (wallet_address, last_claim_at)
                VALUES ($1, NOW())
                ON CONFLICT (wallet_address) DO UPDATE SET last_claim_at = NOW()
                """,
                wallet_address,
            )
