"""Unit tests: name generation, slugs, transitions, immutability, ID derivation."""
from datetime import datetime, timezone

import pytest

from xleuth_shared.baskets import (
    assert_mutable_update,
    basket_id_from_slug,
    generate_name,
    legacy_basket_id_from_name,
    make_slug,
    validate_transition,
)


def test_generate_name_single_function():
    assert generate_name("TOP", 20, datetime(2026, 10, 31, tzinfo=timezone.utc)) == "TOP20-OCTOBER-2026"
    assert generate_name("top", 20, datetime(2026, 10, 31, tzinfo=timezone.utc)) == "TOP20-OCTOBER-2026"
    assert generate_name("CRYPTO", 5, datetime(2027, 1, 15, tzinfo=timezone.utc)) == "CRYPTO5-JANUARY-2027"


def test_make_slug_includes_year():
    assert make_slug("TOP", 20, datetime(2026, 10, 31, tzinfo=timezone.utc)) == "top20-2026-10"
    # October repeats yearly -> slugs differ, names don't
    assert make_slug("TOP", 20, datetime(2027, 10, 31, tzinfo=timezone.utc)) == "top20-2027-10"


def test_exclusive_month_boundary_labels_the_month_that_just_closed():
    expiry = datetime(2027, 2, 1, tzinfo=timezone.utc)
    assert generate_name("TOP", 20, expiry) == "TOP20-JANUARY-2027"
    assert make_slug("TOP", 20, expiry) == "top20-2027-01"
    rollover = datetime(2028, 1, 1, tzinfo=timezone.utc)
    assert generate_name("TOP", 20, rollover) == "TOP20-DECEMBER-2027"
    assert make_slug("TOP", 20, rollover) == "top20-2027-12"


def test_validation():
    with pytest.raises(ValueError):
        generate_name("TOP", 0, datetime(2026, 10, 31, tzinfo=timezone.utc))
    with pytest.raises(ValueError):
        generate_name("bad-theme!", 20, datetime(2026, 10, 31, tzinfo=timezone.utc))
    from xleuth_shared.baskets import validate_window
    with pytest.raises(ValueError):
        validate_window(datetime(2026, 10, 31, tzinfo=timezone.utc),
                        datetime(2026, 10, 1, tzinfo=timezone.utc))


def test_transitions():
    validate_transition("draft", "registering")
    validate_transition("registering", "active")
    validate_transition("registering", "registration_failed")
    validate_transition("registration_failed", "registering")
    validate_transition("active", "closed")
    validate_transition("active", "settled")
    validate_transition("closed", "settled")
    with pytest.raises(ValueError):
        validate_transition("draft", "active")
    with pytest.raises(ValueError):
        validate_transition("active", "draft")
    with pytest.raises(ValueError):
        validate_transition("settled", "active")


def test_immutability_after_draft():
    assert_mutable_update("draft", {"theme", "selection_rules"})
    with pytest.raises(ValueError):
        assert_mutable_update("active", {"theme"})
    with pytest.raises(ValueError):
        assert_mutable_update("registering", {"selection_rules"})
    # non-frozen fields are fine
    assert_mutable_update("registering", {"onchain_index_id"})


def test_id_derivation_differs_by_design():
    # Legacy: keccak(NAME); new: keccak(slug). Both 32 bytes, different values.
    old = legacy_basket_id_from_name("TOP20-JULY")
    new = basket_id_from_slug("top20-2026-07")
    assert len(old) == 32 and len(new) == 32 and old != new
    # Deterministic
    assert basket_id_from_slug("top20-2026-10") == basket_id_from_slug("top20-2026-10")
