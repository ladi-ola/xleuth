"""Unit tests for the Explore page section classifier (PLAN.md task 2).

Rule: Resolved first, then Active, then Upcoming.
  Active   = seeded (constituent markets mapped) AND trading on Polymarket
             (the latest snapshot computed at least one live price).
  Upcoming = not seeded, or seeded but not yet trading on Polymarket.
  Resolved = the existing resolved logic (registry closed/settled, expiry
             passed, or name-derived lifecycle ended) — unchanged.

The verification case is TOP20-NOVEMBER being live and trading while its name
targets next month; the classifier must never key off the name for Active.
"""

from datetime import datetime, timezone

from xleuth_shared.basket_lifecycle import (
    STATUS_ACTIVE,
    STATUS_RESOLVED,
    STATUS_UPCOMING,
    classify_index_status,
    is_resolved,
)

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


def test_active_when_seeded_and_trading_even_if_name_is_next_month():
    # TOP20-NOVEMBER: name targets next month but its markets are live/priced.
    status, tradeable = classify_index_status(
        "TOP20-NOVEMBER", constituent_count=20, index_price=0.0022, now=NOW
    )
    assert status == STATUS_ACTIVE
    assert tradeable is True


def test_active_with_registry_row_unexpired():
    row = {
        "status": "active",
        "expiry_at": datetime(2026, 11, 30, tzinfo=timezone.utc),
    }
    status, tradeable = classify_index_status(
        "TOP20-OCTOBER",
        registry_row=row,
        constituent_count=20,
        index_price=36.92,
        now=NOW,
    )
    assert status == STATUS_ACTIVE
    assert tradeable is True


def test_upcoming_when_seeded_but_not_trading():
    # Constituent markets mapped, but no live price (Polymarket not trading).
    status, tradeable = classify_index_status(
        "TOP20-NOVEMBER", constituent_count=20, index_price=None, now=NOW
    )
    assert status == STATUS_UPCOMING
    assert tradeable is False


def test_upcoming_when_no_markets_mapped():
    # Known basket (registry row, e.g. registering) with no constituents yet.
    row = {
        "status": "registering",
        "expiry_at": datetime(2026, 11, 30, tzinfo=timezone.utc),
    }
    for count in (None, 0):
        status, tradeable = classify_index_status(
            "TOP20-NOVEMBER",
            registry_row=row,
            constituent_count=count,
            index_price=None,
            now=NOW,
        )
        assert status == STATUS_UPCOMING
        assert tradeable is False


def test_resolved_wins_over_active_signals():
    for reg_status in ("closed", "settled"):
        row = {
            "status": reg_status,
            "expiry_at": datetime(2026, 11, 30, tzinfo=timezone.utc),
        }
        status, tradeable = classify_index_status(
            "TOP20-OCTOBER",
            registry_row=row,
            constituent_count=20,
            index_price=36.92,
            now=NOW,
        )
        assert status == STATUS_RESOLVED, reg_status
        assert tradeable is False


def test_resolved_when_name_month_has_passed():
    # No registry row; October index viewed in December -> resolved.
    later = datetime(2026, 12, 5, tzinfo=timezone.utc)
    status, tradeable = classify_index_status(
        "TOP20-OCTOBER", constituent_count=20, index_price=36.92, now=later
    )
    assert status == STATUS_RESOLVED
    assert tradeable is False


def test_resolved_when_registry_expiry_passed():
    row = {
        "status": "active",
        "expiry_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
    }
    status, _ = classify_index_status(
        "TOP20-OCTOBER",
        registry_row=row,
        constituent_count=20,
        index_price=36.92,
        now=NOW,
    )
    assert status == STATUS_RESOLVED


def test_precedence_resolved_then_active_then_upcoming_is_exhaustive():
    # Every branch returns exactly one of the three section values.
    cases = [
        {"registry_row": {"status": "closed", "expiry_at": None}},
        {"constituent_count": 20, "index_price": 1.0},
        {"constituent_count": 20, "index_price": None},
        {"constituent_count": 0, "index_price": None},
    ]
    for kwargs in cases:
        status, _ = classify_index_status("TOP20-NOVEMBER", now=NOW, **kwargs)
        assert status in {STATUS_ACTIVE, STATUS_UPCOMING, STATUS_RESOLVED}


def test_transient_failure_defaults_to_upcoming():
    # A missing/unknown snapshot must not be advertised as trading.
    status, tradeable = classify_index_status("TOP20-NOVEMBER", now=NOW)
    assert status == STATUS_UPCOMING
    assert tradeable is False


def test_is_resolved_helper_matches_registry_and_name_rules():
    assert is_resolved("TOP20-NOVEMBER", None, NOW) is False
    assert is_resolved("TOP20-OCTOBER", None, NOW) is False
    assert (
        is_resolved(
            "TOP20-NOVEMBER",
            {"status": "closed", "expiry_at": datetime(2026, 11, 30, tzinfo=timezone.utc)},
            NOW,
        )
        is True
    )
    assert (
        is_resolved(
            "TOP20-OCTOBER",
            {"status": "active", "expiry_at": datetime(2026, 10, 1, tzinfo=timezone.utc)},
            NOW,
        )
        is True
    )
