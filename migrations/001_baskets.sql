-- Migration 001: baskets registry (PLAN.md DB table: baskets)
-- Reversible: see down/001_baskets.down.sql
-- Owner: data-ingestion ensure_schema() also executes this; the migration
-- files exist so operators can apply/roll back explicitly against a copy
-- of current data (quality bar: reversible, tested migration).
-- Uses plain CREATE TABLE IF NOT EXISTS so concurrent service boot is safe.

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
