"""Durable, single-slot Postgres journal for the V2 signed atomic relayer.

Pending signed bytes are stored before broadcast and survive worker restart.
The primary key serializes submissions for one relayer across processes.
Never store private keys in this table or use a local file on Render.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from xleuth_matching.relayed_execution import PendingRelay

_SCHEMA = """
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
)
"""


class PostgresRelayJournal:
    """Synchronous journal for ``AtomicRelaySubmitter``'s worker thread.

    psycopg's connection context commits only after each state transition;
    rollback on any exception preserves the pending transaction for recovery.
    """

    def __init__(self, dsn: str, connect: Callable | None = None):
        if not dsn:
            raise ValueError("DATABASE_URL is required for durable atomic execution")
        if connect is None:
            import psycopg
            connect = psycopg.connect
        self._connect = connect
        self._dsn = dsn

    def ensure_schema(self) -> None:
        with self._connect(self._dsn) as db:
            db.execute(_SCHEMA)

    def pending(self, chain_id: int, relayer: str) -> PendingRelay | None:
        with self._connect(self._dsn) as db:
            row = db.execute(
                "SELECT tx_hash, match_count, raw_transaction, executor, expected_matches "
                "FROM atomic_relay_journal WHERE chain_id=%s AND relayer=%s AND status='pending'",
                (chain_id, relayer.lower()),
            ).fetchone()
        if row is None:
            return None
        encoded = row[4] if isinstance(row[4], list) else json.loads(row[4])
        expected = tuple(
            (bytes.fromhex(item[0]), bytes.fromhex(item[1]), bytes.fromhex(item[2]),
             *item[3:]) for item in encoded
        )
        return PendingRelay(row[0], row[1], bytes(row[2]), row[3], expected)

    def record_signed(self, chain_id: int, relayer: str, pending: PendingRelay) -> None:
        expected = [
            [item[0].hex(), item[1].hex(), item[2].hex(), *item[3:]]
            for item in pending.expected_matches
        ]
        with self._connect(self._dsn) as db:
            row = db.execute(
                "INSERT INTO atomic_relay_journal "
                "(chain_id,relayer,tx_hash,executor,raw_transaction,match_count,expected_matches,status) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,'pending') "
                "ON CONFLICT (chain_id,relayer) DO UPDATE SET "
                "tx_hash=EXCLUDED.tx_hash, executor=EXCLUDED.executor, "
                "raw_transaction=EXCLUDED.raw_transaction, match_count=EXCLUDED.match_count, "
                "expected_matches=EXCLUDED.expected_matches, status='pending', "
                "block_number=NULL, updated_at=now() "
                "WHERE atomic_relay_journal.status <> 'pending' RETURNING tx_hash",
                (chain_id, relayer.lower(), pending.tx_hash, pending.executor,
                 pending.raw_transaction, pending.match_count, json.dumps(expected)),
            ).fetchone()
            if row is None:
                raise ValueError("a signed relayer transaction is already pending; reconcile first")

    def record_receipt(self, chain_id: int, relayer: str, tx_hash: str, receipt: dict) -> None:
        status = receipt["status"]
        block = receipt["blockNumber"]
        if type(status) is not int or status not in (0, 1) or type(block) is not int or block < 0:
            raise ValueError("receipt must have a final status and block")
        with self._connect(self._dsn) as db:
            row = db.execute(
                "UPDATE atomic_relay_journal SET status=%s, block_number=%s, updated_at=now() "
                "WHERE chain_id=%s AND relayer=%s AND tx_hash=%s AND status='pending' "
                "RETURNING tx_hash",
                ("confirmed" if status == 1 else "reverted", block,
                 chain_id, relayer.lower(), tx_hash),
            ).fetchone()
            if row is None:
                raise ValueError("journal has no matching pending transaction")
