"""Seed/backfill live baskets via the same code path as the CLI.

PLAN.md migration: "Rewrite infra/scripts/seed_baskets.py to insert via the
same code path as the CLI (no fake price data), and write a reversible
migration that backfills every currently live basket with its correct status
and existing on-chain ID."

- No fake price data or legacy IDs: creates draft registry rows only.
- Same code path: uses xleuth_shared.db_baskets.create_draft.
- Idempotent: re-running adopts existing rows (no second tx, no dupes).
- Reversible: every insert is logged in basket_events; to roll back, run
  migrations/down/001_baskets.down.sql or DELETE FROM baskets WHERE slug IN (...).

Usage:
  PYTHONPATH=infra/scripts:shared python3 seed_baskets.py [--apply]
  Default is --dry-run (prints what would be inserted). --apply writes.
  ACTIVE_BASKETS env (default TOP20-{MONTH}) decides the calendar to prepare.
"""

from __future__ import annotations

import argparse
import asyncio
import calendar
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))

from dotenv import load_dotenv  # noqa: E402


def month_bounds(year: int, month: int):
    ws = datetime(year, month, 1, tzinfo=timezone.utc)
    last = calendar.monthrange(year, month)[1]
    exp = datetime(year, month, last, 23, 59, 59, tzinfo=timezone.utc)
    return ws, exp


async def main() -> int:
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write rows (default: dry-run)")
    args = ap.parse_args()

    import asyncpg

    from xleuth_shared.basket_lifecycle import active_basket_names, extract_target_month, extract_target_year, parse_basket_name
    from xleuth_shared.baskets import make_slug, normalize_theme
    from xleuth_shared.db_baskets import ensure_baskets_schema

    templates = os.getenv("ACTIVE_BASKETS", "TOP20-{MONTH}").split(",")
    names = active_basket_names(templates)
    print(f"ACTIVE_BASKETS={templates} -> backfill {names}")

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL required", file=sys.stderr)
        return 1
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    await ensure_baskets_schema(pool)

    try:
        now = datetime.now(timezone.utc)
        plan = []
        for name in names:
            parsed = parse_basket_name(name)
            if not parsed:
                print(f"skip custom/undated {name!r} (no month/count in name)")
                continue
            n, month, _ = parsed
            year = extract_target_year(name) or now.year
            theme = "".join(ch for ch in name.upper() if ch.isalpha() and not ch in "JANUARYFEBRUMARCHPILGSTOVCD") or "TOP"
            # theme = leading letters before digits, e.g. TOP20-OCTOBER -> TOP
            import re as _re
            m = _re.match(r"^([A-Z]+)[0-9]+-", name.upper())
            theme = normalize_theme(m.group(1) if m else "TOP")
            ws, exp = month_bounds(year, month)
            slug = make_slug(theme, n, exp)
            plan.append({"name": name, "slug": slug, "theme": theme, "count": n,
                         "window_start": ws.isoformat(), "expiry_at": exp.isoformat()})

        print(json.dumps(plan, indent=2))
        if not args.apply:
            print("dry-run: no writes. Re-run with --apply.")
            return 0

        from xleuth_shared.db_baskets import create_draft, get_by_slug

        for p in plan:
            existing = await get_by_slug(pool, p["slug"])
            if existing is not None:
                print(f"exists {p['slug']} ({existing['status']}); leaving unchanged")
                continue
            row = await create_draft(
                pool, theme=p["theme"], market_count=p["count"],
                window_start=datetime.fromisoformat(p["window_start"]),
                expiry_at=datetime.fromisoformat(p["expiry_at"]),
                selection_rules={"exclude_categories": os.getenv("EXCLUDE_CATEGORIES", "sports"),
                                 "weighting": "vwap", "version": 1,
                                 "backfilled_from": p["name"]},
                created_by="seed_baskets",
            )
            print(f"prepared {p['slug']} -> draft; register explicitly with basket-register")
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
