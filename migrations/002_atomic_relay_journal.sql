-- Durable signed-transaction slot per chain/relayer. Apply only to a test DB
-- before enabling atomic execution; DO NOT apply to hosted data without approval.
CREATE TABLE IF NOT EXISTS atomic_relay_journal (
    chain_id BIGINT NOT NULL,
    relayer TEXT NOT NULL,
    tx_hash TEXT NOT NULL,
    executor TEXT NOT NULL,
    raw_transaction BYTEA NOT NULL,
    match_count INTEGER NOT NULL,
    expected_matches JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'confirmed', 'reverted')),
    block_number BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (chain_id, relayer)
);
