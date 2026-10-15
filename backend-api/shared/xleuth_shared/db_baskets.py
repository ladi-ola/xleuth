"""Shared asyncpg data layer for the baskets registry (raw SQL, no ORM).

Per user decision 2026-10-09: raw asyncpg + SQL files, consistent with the
existing ensure_schema() pattern. Immutability + status transitions are
enforced HERE (data layer), not only in the CLI, per PLAN.md.

Tables (see migrations/001_baskets.sql):
  baskets(slug unique, theme/market_count/expiry..., status, onchain ids)
  basket_events(basket_id, event, actor, payload, created_at) append-only.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from xleuth_shared.baskets import (
    assert_mutable_update,
    generate_name,
    make_slug,
    normalize_theme,
    validate_market_count,
    validate_transition,
    validate_window,
)

BASKETS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS baskets (
    id SERIAL PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    theme TEXT NOT NULL,
    market_count INTEGER NOT NULL CHECK (market_count > 0),
    window_start TIMESTAMPTZ NOT NULL,
    expiry_at TIMESTAMPTZ NOT NULL,
    settlement_at TIMESTAMPTZ,
    selection_rules JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','registering','active','closed','settled','registration_failed')),
    onchain_index_id TEXT,
    register_tx_hash TEXT,
    registered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by TEXT,
    CONSTRAINT uq_basket_theme_count_expiry UNIQUE (theme, market_count, expiry_at),
    CONSTRAINT ck_basket_expiry_after_window CHECK (expiry_at > window_start)
);

CREATE TABLE IF NOT EXISTS basket_events (
    id SERIAL PRIMARY KEY,
    basket_id INTEGER NOT NULL REFERENCES baskets(id) ON DELETE CASCADE,
    event TEXT NOT NULL,
    actor TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_baskets_status ON baskets(status);
CREATE INDEX IF NOT EXISTS idx_basket_events_basket ON basket_events(basket_id);
"""


async def ensure_baskets_schema(pool) -> None:
    async with pool.acquire() as conn:
        for statement in BASKETS_TABLE_SQL.split(";"):
            stmt = statement.strip()
            if stmt:
                await conn.execute(stmt)


def _row_to_dict(row) -> dict[str, Any]:
    d = dict(row)
    rules = d.get("selection_rules")
    if isinstance(rules, str):
        d["selection_rules"] = json.loads(rules)
    return d


async def log_event(conn, basket_id: int, event: str, actor: str | None, payload: dict | None = None) -> None:
    await conn.execute(
        "INSERT INTO basket_events (basket_id, event, actor, payload) VALUES ($1, $2, $3, $4::jsonb)",
        basket_id, event, actor, json.dumps(payload or {}),
    )


async def create_draft(pool, *, theme: str, market_count: int, window_start: datetime,
                       expiry_at: datetime, selection_rules: dict | None = None,
                       created_by: str | None = None) -> dict[str, Any]:
    t = normalize_theme(theme)
    n = validate_market_count(market_count)
    validate_window(window_start, expiry_at)
    slug = make_slug(t, n, expiry_at)
    name = generate_name(t, n, expiry_at)
    rules = selection_rules or {}
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """INSERT INTO baskets
                   (slug, name, theme, market_count, window_start, expiry_at,
                    selection_rules, status, created_by)
                   VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,'draft',$8)
                   ON CONFLICT (slug) DO NOTHING
                   RETURNING *""",
                slug, name, t, n, window_start, expiry_at, json.dumps(rules), created_by,
            )
            if row is None:
                raise ValueError(f"Basket slug {slug!r} already exists")
            await log_event(conn, row["id"], "created", created_by, {"slug": slug, "name": name})
            return _row_to_dict(row)


async def get_by_slug(pool, slug: str) -> dict[str, Any] | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM baskets WHERE slug = $1", slug)
        return _row_to_dict(row) if row else None


async def list_baskets(pool, status: str | None = None) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        if status:
            rows = await conn.fetch("SELECT * FROM baskets WHERE status = $1 ORDER BY expiry_at", status)
        else:
            rows = await conn.fetch("SELECT * FROM baskets ORDER BY expiry_at")
        return [_row_to_dict(r) for r in rows]


async def list_active(pool, now: datetime | None = None) -> list[dict[str, Any]]:
    """Baskets services should process: status=active AND not past expiry."""
    now = now or datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM baskets WHERE status = 'active' AND expiry_at > $1 ORDER BY expiry_at",
            now,
        )
        return [_row_to_dict(r) for r in rows]


async def transition(pool, slug: str, new_status: str, actor: str | None = None,
                     payload: dict | None = None, **fields) -> dict[str, Any]:
    """Validate transition + immutability, apply field updates, audit-log."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("SELECT * FROM baskets WHERE slug = $1 FOR UPDATE", slug)
            if row is None:
                raise ValueError(f"Unknown basket slug {slug!r}")
            old = dict(row)
            validate_transition(old["status"], new_status)
            if fields:
                assert_mutable_update(old["status"], set(fields))
            sets = ["status = $2", "updated_at = NOW()"]
            params: list[Any] = [slug, new_status]
            idx = 3
            for k, v in fields.items():
                if k not in {"onchain_index_id", "register_tx_hash", "registered_at",
                             "settlement_at", "selection_rules"}:
                    raise ValueError(f"Field {k!r} cannot be updated via transition()")
                sets.append(f"{k} = ${idx}")
                params.append(json.dumps(v) if k == "selection_rules" else v)
                idx += 1
            updated = await conn.fetchrow(
                f"UPDATE baskets SET {', '.join(sets)} WHERE slug = $1 RETURNING *", *params
            )
            await log_event(conn, old["id"], f"status:{old['status']}->{new_status}",
                            actor, payload or {})
            return _row_to_dict(updated)
