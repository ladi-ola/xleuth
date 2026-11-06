"""Hermetic Postgres journal contract checks (no hosted DB or RPC)."""

from unittest.mock import MagicMock

import pytest

from xleuth_matching.relay_journal import PostgresRelayJournal
from xleuth_matching.relayed_execution import PendingRelay


def _journal(row):
    cursor = MagicMock()
    cursor.fetchone.return_value = row
    db = MagicMock()
    db.execute.return_value = cursor
    context = MagicMock()
    context.__enter__.return_value = db
    journal = PostgresRelayJournal("postgres://example.invalid/test", connect=lambda _dsn: context)
    return journal, db


def _pending():
    return PendingRelay(
        "0xtx", 1, b"signed-public-transaction", "0xexecutor",
        ((b"a" * 32, b"b" * 32, b"c" * 32, 200_000, 50_000, 10_000_000),),
    )


def test_recover_pending_raw_transaction_and_expected_fills():
    journal, _ = _journal((
        "0xtx", 1, memoryview(b"signed-public-transaction"), "0xexecutor",
        [["61" * 32, "62" * 32, "63" * 32, 200_000, 50_000, 10_000_000]],
    ))
    assert journal.pending(80002, "0xRELAYER") == _pending()


def test_pending_transaction_cannot_be_overwritten():
    journal, db = _journal(None)
    with pytest.raises(ValueError, match="already pending"):
        journal.record_signed(80002, "0xRELAYER", _pending())
    statement, values = db.execute.call_args.args
    assert "ON CONFLICT" in statement and "status <> 'pending'" in statement
    assert values[1] == "0xrelayer"
    assert values[4] == b"signed-public-transaction"


def test_receipt_requires_final_status_and_matching_pending_hash():
    journal, _ = _journal(None)
    with pytest.raises(ValueError, match="final status"):
        journal.record_receipt(80002, "0xrelayer", "0xtx", {"status": True, "blockNumber": 4})
    with pytest.raises(ValueError, match="no matching pending"):
        journal.record_receipt(80002, "0xrelayer", "0xtx", {"status": 1, "blockNumber": 4})
