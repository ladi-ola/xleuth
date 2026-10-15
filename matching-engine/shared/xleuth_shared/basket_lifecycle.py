"""Basket lifecycle: automatic month-based index rotation.

The ACTIVE_BASKETS env var supports two kinds of entries:

  * Literal dated baskets, e.g. "TOP20-AUGUST" — used as-is. A basket whose
    target month has already ended is *resolved*: it is no longer updated or
    tradeable, but its rows stay in the database as queryable history.

  * Month templates, e.g. "TOP20-{MONTH}", "<MONTH>", "%MONTH%", or the
    phrase "MONTH_OF_THE_YEAR" / "MONTH OF THE YEAR" / "MONTH-OF-THE-YEAR".
    Each template expands to the current month (active) and the next month
    (upcoming), so the index roster rotates automatically every month with
    no config edits. The next month is seeded in advance ("prepping").

Naming: a dated basket is "<FAMILY><SIZE>-<MONTH>", e.g. TOP20-AUGUST. An
optional year suffix "-YYYY" (e.g. TOP20-JANUARY-2027) disambiguates across
year boundaries; year-less names refer to the current calendar year. When a
template is expanded across the December/January boundary, the rollover
month is rendered with the year suffix automatically. Templates may also
carry a {YEAR} (or <YEAR>/%YEAR%) placeholder.

Tradeability: any basket that has NOT reached its resolution time (end of
its target month) is tradeable — this includes current, upcoming and future
dated baskets as well as undated/custom baskets. Only resolved baskets are
read-only (history still queryable).
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone

FULL_MONTH_NAMES = [
    "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
    "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER",
]

MONTH_NAMES = {
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4,
    "MAY": 5, "JUNE": 6, "JULY": 7, "AUGUST": 8,
    "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4,
    "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8,
    "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

MONTH_NAMES_REVERSE = {idx: name for idx, name in enumerate(FULL_MONTH_NAMES, start=1)}

STATUS_ACTIVE = "active"
STATUS_UPCOMING = "upcoming"
STATUS_RESOLVED = "resolved"

# Strict form: family letters + size digits + month (+ optional year).
_BASKET_RE = re.compile(r"^([A-Z]+)([0-9]+)-([A-Z]+)(?:-([0-9]{4}))?$")
# Lenient form: anything ending in -<MONTH> (with optional -YYYY).
_DATED_RE = re.compile(r"^(.+)-([A-Z]+)(?:-([0-9]{4}))?$")

_MONTH_MARKER_RES = [
    re.compile(r"\{MONTH\}", re.IGNORECASE),
    re.compile(r"<MONTH>", re.IGNORECASE),
    re.compile(r"%MONTH%", re.IGNORECASE),
]
_YEAR_MARKER_RES = [
    re.compile(r"\{YEAR\}", re.IGNORECASE),
    re.compile(r"<YEAR>", re.IGNORECASE),
    re.compile(r"%YEAR%", re.IGNORECASE),
]
_MONTH_PHRASE_RE = re.compile(
    r"\bMONTH(?:_|\s|-)*OF(?:_|\s|-)*THE(?:_|\s|-)*YEAR\b", re.IGNORECASE
)
_BARE_MONTH_RE = re.compile(r"\bMONTH\b", re.IGNORECASE)


def parse_basket_name(name: str) -> tuple[int, int, str] | None:
    """Parse `<FAMILY><SIZE>-<MONTH>[-YYYY]` (e.g. TOP20-AUGUST) -> (size, month, name)."""
    m = _BASKET_RE.match(name.upper())
    if not m:
        return None
    month_num = MONTH_NAMES.get(m.group(3))
    if month_num is None:
        return None
    return int(m.group(2)), month_num, name


def extract_target_month(name: str) -> int | None:
    """Month number (1-12) a basket is dated for, or None if it has no month."""
    m = _DATED_RE.match(name.upper())
    if not m:
        return None
    return MONTH_NAMES.get(m.group(2))


def extract_target_year(name: str) -> int | None:
    """Explicit year (if any) in a dated basket name, e.g. 2027 for TOP20-JAN-2027."""
    m = _DATED_RE.match(name.upper())
    if not m:
        return None
    return int(m.group(3)) if m.group(3) else None


def is_dated_basket(name: str) -> bool:
    return extract_target_month(name) is not None


def is_template(name: str) -> bool:
    """True if the entry carries a month placeholder instead of a concrete month."""
    if any(r.search(name) for r in _MONTH_MARKER_RES):
        return True
    if _MONTH_PHRASE_RE.search(name):
        return True
    return bool(_BARE_MONTH_RE.search(name))


def render_month_template(template: str, month: int, year: int | None = None) -> str:
    """Substitute a month (1-12) into a template, e.g. TOP20-{MONTH} -> TOP20-AUGUST.

    A {YEAR} (or <YEAR>/%YEAR%) marker is substituted when `year` is given.
    """
    month_name = MONTH_NAMES_REVERSE[month]
    out = template
    for r in _MONTH_MARKER_RES:
        out = r.sub(month_name, out)
    out = _MONTH_PHRASE_RE.sub(month_name, out)
    out = _BARE_MONTH_RE.sub(month_name, out)
    if year is not None:
        for r in _YEAR_MARKER_RES:
            out = r.sub(str(year), out)
    return out


def has_year_marker(template: str) -> bool:
    return any(r.search(template) for r in _YEAR_MARKER_RES)


def basket_status(name: str, now: datetime | None = None) -> str:
    """Lifecycle status of a basket: active | upcoming | resolved.

    Resolution time is the end of the basket's target month. Year-less names
    refer to the current calendar year. Undated baskets never resolve and
    are always active.
    """
    now = now or datetime.now(timezone.utc)
    month = extract_target_month(name)
    if month is None:
        return STATUS_ACTIVE
    year = extract_target_year(name)
    if year is None:
        year = now.year
    if year < now.year:
        return STATUS_RESOLVED
    if year > now.year:
        return STATUS_UPCOMING
    if month == now.month:
        return STATUS_ACTIVE
    if month < now.month:
        return STATUS_RESOLVED
    return STATUS_UPCOMING


def is_tradeable(name: str, now: datetime | None = None) -> bool:
    """A basket is tradeable until it resolves (end of its target month)."""
    return basket_status(name, now) != STATUS_RESOLVED


@dataclass
class BasketDescriptor:
    basket_name: str
    status: str
    is_tradeable: bool
    month: int | None = None
    source_template: str | None = None


def expand_basket_templates(
    templates: list[str], now: datetime | None = None
) -> list[BasketDescriptor]:
    """Expand the ACTIVE_BASKETS list into concrete baskets with lifecycle status.

    Templates yield the current month (active) plus the next month (upcoming,
    prepped in advance). Literal entries are passed through with their status
    computed from the name.
    """
    now = now or datetime.now(timezone.utc)
    out: list[BasketDescriptor] = []
    seen: set[str] = set()
    for raw in templates:
        entry = (raw or "").strip()
        if not entry:
            continue
        if is_template(entry):
            current = render_month_template(entry, now.month, now.year)
            next_month = 1 if now.month == 12 else now.month + 1
            next_year = now.year + 1 if now.month == 12 else now.year
            nxt = render_month_template(entry, next_month, next_year)
            if now.month == 12 and not has_year_marker(entry):
                # Year-less names refer to the current year; disambiguate the
                # January rollover with an explicit year suffix.
                nxt = f"{nxt}-{next_year}"
            candidates = [
                BasketDescriptor(current, STATUS_ACTIVE, True, now.month, entry),
                BasketDescriptor(nxt, STATUS_UPCOMING, True, next_month, entry),
            ]
        else:
            candidates = [
                BasketDescriptor(
                    entry,
                    basket_status(entry, now),
                    is_tradeable(entry, now),
                    extract_target_month(entry),
                    None,
                )
            ]
        for desc in candidates:
            if desc.basket_name in seen:
                continue
            seen.add(desc.basket_name)
            out.append(desc)
    return out


def active_basket_names(templates: list[str], now: datetime | None = None) -> list[str]:
    """Concrete basket names the ingestion should keep building (not resolved)."""
    return [
        d.basket_name
        for d in expand_basket_templates(templates, now)
        if d.status != STATUS_RESOLVED
    ]
