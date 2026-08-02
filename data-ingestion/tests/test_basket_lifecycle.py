from datetime import datetime, timezone

from xleuth_shared.basket_lifecycle import (
    STATUS_ACTIVE,
    STATUS_RESOLVED,
    STATUS_UPCOMING,
    active_basket_names,
    basket_status,
    expand_basket_templates,
    extract_target_month,
    is_dated_basket,
    is_template,
    is_tradeable,
    parse_basket_name,
    render_month_template,
)

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)


# ── Name parsing ───────────────────────────────────────────────────────


def test_parse_basket_name():
    assert parse_basket_name("TOP20-AUGUST") == (20, 8, "TOP20-AUGUST")
    assert parse_basket_name("TOP100-AUGUST") == (100, 8, "TOP100-AUGUST")
    assert parse_basket_name("CRYPTO20-SEPTEMBER") == (20, 9, "CRYPTO20-SEPTEMBER")
    assert parse_basket_name("invalid") is None
    assert parse_basket_name("TOP-ABC") is None
    assert parse_basket_name("TOP20-NOTAMONTH") is None


def test_extract_target_month():
    assert extract_target_month("TOP20-AUGUST") == 8
    assert extract_target_month("CRYPTO-AUGUST") == 8
    assert extract_target_month("MY-CUSTOM") is None
    assert is_dated_basket("TOP20-JULY") is True
    assert is_dated_basket("MY-CUSTOM") is False


# ── Lifecycle status / tradeability ────────────────────────────────────


def test_basket_status():
    assert basket_status("TOP20-JULY", NOW) == STATUS_RESOLVED
    assert basket_status("TOP20-AUGUST", NOW) == STATUS_ACTIVE
    assert basket_status("TOP20-SEPTEMBER", NOW) == STATUS_UPCOMING
    assert basket_status("TOP20-DECEMBER", NOW) == STATUS_UPCOMING
    assert basket_status("MY-CUSTOM", NOW) == STATUS_ACTIVE


def test_is_tradeable():
    assert is_tradeable("TOP20-JULY", NOW) is False
    assert is_tradeable("TOP20-AUGUST", NOW) is True
    assert is_tradeable("TOP20-SEPTEMBER", NOW) is True
    assert is_tradeable("TOP20-DECEMBER", NOW) is True
    assert is_tradeable("MY-CUSTOM", NOW) is True


def test_basket_status_january_rollover():
    jan = datetime(2027, 1, 10, tzinfo=timezone.utc)
    # Year-less names refer to the current calendar year.
    assert basket_status("TOP20-DECEMBER", jan) == STATUS_UPCOMING
    # Explicit years disambiguate past/next occurrences.
    assert basket_status("TOP20-DECEMBER-2026", jan) == STATUS_RESOLVED
    assert basket_status("TOP20-JANUARY", jan) == STATUS_ACTIVE
    assert basket_status("TOP20-JANUARY-2027", jan) == STATUS_ACTIVE
    assert basket_status("TOP20-FEBRUARY", jan) == STATUS_UPCOMING
    assert is_tradeable("TOP20-DECEMBER-2026", jan) is False


# ── Templates ───────────────────────────────────────────────────────────


def test_is_template():
    assert is_template("TOP20-{MONTH}")
    assert is_template("TOP20-<MONTH>")
    assert is_template("TOP20-%MONTH%")
    assert is_template("TOP20-MONTH_OF_THE_YEAR")
    assert is_template("TOP20-MONTH OF THE YEAR")
    assert is_template("TOP20-MONTH-OF-THE-YEAR")
    assert not is_template("TOP20-AUGUST")
    assert not is_template("TOP20-MONTHLY")


def test_render_month_template():
    assert render_month_template("TOP20-{MONTH}", 8) == "TOP20-AUGUST"
    assert render_month_template("TOP20-MONTH_OF_THE YEAR", 8) == "TOP20-AUGUST"
    assert render_month_template("TOP20-MONTH_OF_THE_YEAR", 8) == "TOP20-AUGUST"
    assert render_month_template("TOP20-MONTH OF THE YEAR", 9) == "TOP20-SEPTEMBER"
    assert render_month_template("TOP20-{MONTH}-{YEAR}", 9, 2027) == "TOP20-SEPTEMBER-2027"
    assert render_month_template("TOP20-{MONTH}", 8, 2026) == "TOP20-AUGUST"


def test_expand_basket_templates():
    descs = expand_basket_templates(
        ["TOP20-{MONTH}", "TOP20-MONTH_OF_THE_YEAR", "TOP20-JULY"], NOW
    )
    by_name = {d.basket_name: d for d in descs}
    assert set(by_name) == {
        "TOP20-AUGUST",
        "TOP20-SEPTEMBER",
        "TOP20-JULY",
    }

    august = by_name["TOP20-AUGUST"]
    assert august.status == STATUS_ACTIVE
    assert august.is_tradeable is True
    assert august.month == 8

    september = by_name["TOP20-SEPTEMBER"]
    assert september.status == STATUS_UPCOMING
    assert september.is_tradeable is True
    assert september.month == 9

    july = by_name["TOP20-JULY"]
    assert july.status == STATUS_RESOLVED
    assert july.is_tradeable is False


def test_active_basket_names_excludes_resolved():
    names = active_basket_names(["TOP20-{MONTH}", "TOP20-JULY"], NOW)
    assert names == ["TOP20-AUGUST", "TOP20-SEPTEMBER"]


def test_expand_december_rollover():
    dec = datetime(2026, 12, 10, tzinfo=timezone.utc)
    descs = expand_basket_templates(["TOP20-{MONTH}"], dec)
    by_name = {d.basket_name: d for d in descs}
    assert set(by_name) == {"TOP20-DECEMBER", "TOP20-JANUARY-2027"}
    jan = by_name["TOP20-JANUARY-2027"]
    assert jan.status == STATUS_UPCOMING
    assert jan.is_tradeable is True
    assert basket_status("TOP20-JANUARY-2027", dec) == STATUS_UPCOMING


def test_expand_december_rollover_with_year_marker():
    dec = datetime(2026, 12, 10, tzinfo=timezone.utc)
    names = active_basket_names(["TOP20-{MONTH}-{YEAR}"], dec)
    assert names == ["TOP20-DECEMBER-2026", "TOP20-JANUARY-2027"]
    assert basket_status("TOP20-JANUARY-2027", dec) == STATUS_UPCOMING


def test_expand_skips_empty_entries_and_dedupes():
    descs = expand_basket_templates(["", "  ", "TOP20-{MONTH}", "TOP20-AUGUST"], NOW)
    names = [d.basket_name for d in descs]
    assert names == ["TOP20-AUGUST", "TOP20-SEPTEMBER"]


def test_expand_literal_undated_passthrough():
    descs = expand_basket_templates(["MY-CUSTOM"], NOW)
    assert len(descs) == 1
    assert descs[0].basket_name == "MY-CUSTOM"
    assert descs[0].status == STATUS_ACTIVE
    assert descs[0].is_tradeable is True
