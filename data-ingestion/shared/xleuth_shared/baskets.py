"""Single source of truth for basket naming, slugs, IDs and lifecycle.

PLAN.md naming convention (settled):
  Name format: {THEME}{COUNT}-{EXPIRY}-{YEAR}, e.g. TOP20-OCTOBER-2026
  - THEME: what the basket is about (currently "TOP"; future themes allowed).
  - COUNT: number of markets in the basket.
  - EXPIRY: expiry/resolution period, uppercase month name for monthly baskets.

CRITICAL RULES (enforced here, not in each service):
  - The name is a generated display label only. Store theme, market_count and
    expiry_at as separate columns and generate the name in exactly ONE
    function: generate_name(). No service may parse the name to derive
    window, month, count or theme.
  - Because OCTOBER repeats yearly, the immutable unique key is a slug
    including the year, e.g. top20-2026-10. Built only by make_slug().
  - Index ID derivation (per user decision 2026-10-09):
      * Live/legacy baskets: onchain_index_id = keccak256(canonical NAME),
        e.g. keccak("TOP20-JULY"). Preserved verbatim — no redeploy.
      * New baskets: onchain_index_id = keccak256(slug), e.g.
        keccak("top20-2026-10"). Both coexist on-chain because contracts
        accept any bytes32 (setBasketExpiry + pushPrice); the DB column
        records whichever derivation was used.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

FULL_MONTH_NAMES = [
    "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
    "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER",
]

MONTH_NUM_TO_NAME = {i + 1: n for i, n in enumerate(FULL_MONTH_NAMES)}

# Theme: 1-16 uppercase alphanumerics. "TOP" today; CRYPTO/DEFI/etc. tomorrow.
# This intentionally permits "separate indexes different from the format we
# have at the moment" while keeping a structured, generatable name.
_THEME_RE = re.compile(r"^[A-Z0-9]{1,16}$")

STATUS_DRAFT = "draft"
STATUS_REGISTERING = "registering"
STATUS_ACTIVE = "active"
STATUS_CLOSED = "closed"
STATUS_SETTLED = "settled"
STATUS_REGISTRATION_FAILED = "registration_failed"

VALID_STATUSES = frozenset({
    STATUS_DRAFT, STATUS_REGISTERING, STATUS_ACTIVE,
    STATUS_CLOSED, STATUS_SETTLED, STATUS_REGISTRATION_FAILED,
})

# Allowed transitions. Illegal ones raise (enforced in data layer, not CLI).
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_DRAFT: frozenset({STATUS_REGISTERING}),
    STATUS_REGISTERING: frozenset({STATUS_ACTIVE, STATUS_REGISTRATION_FAILED}),
    STATUS_REGISTRATION_FAILED: frozenset({STATUS_REGISTERING}),
    STATUS_ACTIVE: frozenset({STATUS_CLOSED, STATUS_SETTLED}),
    STATUS_CLOSED: frozenset({STATUS_SETTLED}),
    STATUS_SETTLED: frozenset(),
}

# Columns that become immutable once status leaves draft (users hold positions).
IMMUTABLE_AFTER_DRAFT = frozenset({
    "theme", "market_count", "window_start", "expiry_at", "selection_rules",
})


def normalize_theme(theme: str) -> str:
    t = (theme or "").strip().upper()
    if not _THEME_RE.match(t):
        raise ValueError(
            f"Invalid theme {theme!r}: must match {_THEME_RE.pattern} (e.g. TOP, CRYPTO)"
        )
    return t


def validate_market_count(count: int) -> int:
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        raise ValueError(f"market_count must be a positive int, got {count!r}")
    if count > 1000:
        raise ValueError(f"market_count unreasonably large: {count!r}")
    return count


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def resolution_period_end(expiry_at: datetime) -> datetime:
    """Label an exclusive midnight month boundary with the month it closes.

    January's exact expiry is February 1 00:00 UTC, not February's resolution
    window. Existing stored names/IDs are never regenerated or migrated here.
    Legacy within-month expiries keep their existing labels.
    """
    exp = _as_utc(expiry_at)
    if exp.day == 1 and exp.hour == exp.minute == exp.second == exp.microsecond == 0:
        return exp - timedelta(microseconds=1)
    return exp


def generate_name(theme: str, market_count: int, expiry_at: datetime) -> str:
    """THE one function that builds a display name. Nothing may invert it.

    Example: generate_name("TOP", 20, 2026-10-31 UTC) -> "TOP20-OCTOBER".
    """
    t = normalize_theme(theme)
    n = validate_market_count(market_count)
    exp = resolution_period_end(expiry_at)
    month_name = MONTH_NUM_TO_NAME[exp.month]
    return f"{t}{n}-{month_name}-{exp.year}"


def make_slug(theme: str, market_count: int, expiry_at: datetime) -> str:
    """Immutable unique key including the year, e.g. top20-2026-10."""
    t = normalize_theme(theme)
    n = validate_market_count(market_count)
    exp = resolution_period_end(expiry_at)
    return f"{t.lower()}{n}-{exp.year}-{exp.month:02d}"


def validate_window(window_start: datetime, expiry_at: datetime) -> None:
    ws = _as_utc(window_start)
    exp = _as_utc(expiry_at)
    if exp <= ws:
        raise ValueError(f"expiry_at ({exp.isoformat()}) must be > window_start ({ws.isoformat()})")


def validate_transition(old: str, new: str) -> None:
    if old not in VALID_STATUSES:
        raise ValueError(f"Unknown status {old!r}")
    if new not in VALID_STATUSES:
        raise ValueError(f"Unknown status {new!r}")
    if new not in ALLOWED_TRANSITIONS[old]:
        raise ValueError(f"Illegal basket status transition: {old} -> {new}")


def assert_mutable_update(old_status: str, changed_fields: set[str]) -> None:
    """Enforce immutability in the data layer, not only the CLI."""
    if old_status != STATUS_DRAFT:
        frozen = IMMUTABLE_AFTER_DRAFT & set(changed_fields)
        if frozen:
            raise ValueError(
                f"Basket in status {old_status!r} is immutable for fields "
                f"{sorted(frozen)} (users may hold positions)"
            )


def basket_id_from_slug(slug: str) -> bytes:
    """On-chain index ID for NEW baskets: keccak256(slug)."""
    from eth_utils import keccak

    return keccak(text=slug)


def legacy_basket_id_from_name(name: str) -> bytes:
    """On-chain index ID for LIVE/legacy baskets: keccak256(canonical NAME).

    Preserved verbatim so existing Amoy positions keep working with no
    redeploy. Only used by the backfill migration and read paths for rows
    created before the baskets table existed.
    """
    from eth_utils import keccak

    return keccak(text=name)


def default_selection_rules(
    exclude_categories: str = "sports",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Default selection_rules JSON payload (liquidity/weighting overrides).

    Per user decision: risk params (leverage/fees/staleness/tick/size) stay
    GLOBAL in env. Only constituent selection, liquidity filter overrides and
    weighting live here.
    """
    rules: dict[str, Any] = {
        "exclude_categories": exclude_categories,
        "weighting": "vwap",
        "version": 1,
    }
    if extra:
        rules.update(extra)
    return rules
