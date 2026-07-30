"""Diagnose why market_resolves_in_month filters most markets.

Checks the actual format of endDate / endDateIso from the Polymarket Gamma API.
"""
import sys
import os
from datetime import datetime, timezone
from collections import Counter

# Pyright ignore for src import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Copy of the function we're debugging (to run sync)
def market_resolves_in_month(market: dict, target_month: int) -> bool:
    end_date = market.get("endDate") or market.get("endDateIso")
    if not end_date:
        return False
    try:
        dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        return dt.month == target_month
    except (ValueError, TypeError):
        return False


import httpx

GAMMA_BASE = "https://gamma-api.polymarket.com"
LIMIT = 100
MAX_PAGES = 2

all_markets: list[dict] = []

with httpx.Client(timeout=30.0) as client:
    for page in range(MAX_PAGES):
        params = {
            "limit": LIMIT,
            "offset": page * LIMIT,
            "order": "volumeNum",
            "ascending": "false",
            "closed": "false",
            "active": "true",
        }
        resp = client.get(f"{GAMMA_BASE}/markets", params=params)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_markets.extend(batch)
        print(f"  Page {page}: got {len(batch)} markets", flush=True)
        if len(batch) < LIMIT:
            break

print(f"\nTotal markets fetched: {len(all_markets)}")

# ── 1. Inspect endDate / endDateIso fields ─────────────────────────────
print("\n" + "=" * 72)
print("SAMPLE endDate and endDateIso VALUES (first 20 markets)")
print("=" * 72)

for i, m in enumerate(all_markets[:20]):
    ed = m.get("endDate")
    ed_iso = m.get("endDateIso")
    ed_type = type(ed).__name__ if "endDate" in m else "ABSENT"
    ed_iso_type = type(ed_iso).__name__ if "endDateIso" in m else "ABSENT"
    print(f"\n  Market #{i}: id={m.get('id')}")
    print(f"    question: {m.get('question', '')[:80]}")
    print(f"    endDate:   {ed!r:>40}   (type={ed_type})")
    print(f"    endDateIso:{ed_iso!r:>40}   (type={ed_iso_type})")

# ── 2. Check which endDate values are numeric (Unix timestamps) ────────
print("\n" + "=" * 72)
print("endDate VALUE ANALYSIS")
print("=" * 72)

numeric_count = 0
str_count = 0
none_count = 0

for m in all_markets:
    ed = m.get("endDate")
    if ed is None:
        none_count += 1
    elif isinstance(ed, (int, float)):
        numeric_count += 1
    elif isinstance(ed, str):
        str_count += 1

print(f"  endDate is numeric (int/float): {numeric_count}")
print(f"  endDate is string:              {str_count}")
print(f"  endDate is None/missing:        {none_count}")

# ── 3. Check endDateIso presence ───────────────────────────────────────
iso_present = sum(1 for m in all_markets if m.get("endDateIso") is not None)
iso_missing = len(all_markets) - iso_present
print(f"\n  endDateIso present:             {iso_present}")
print(f"  endDateIso missing:             {iso_missing}")

# ── 4. Sample endDateIso string values ─────────────────────────────────
print("\nSAMPLE endDateIso VALUES:")
iso_samples = [m.get("endDateIso") for m in all_markets if m.get("endDateIso") is not None][:10]
for i, v in enumerate(iso_samples):
    print(f"  {i}: {v!r}")

# ── 5. Test the actual market_resolves_in_month function ───────────────
print("\n" + "=" * 72)
print("market_resolves_in_month RESULTS BY MONTH (current function)")
print("=" * 72)

month_resolves = Counter()
for m in all_markets:
    for target in range(1, 13):
        if market_resolves_in_month(m, target):
            month_resolves[target] += 1

month_names = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}

print("  Month  |  Markets resolving")
print("  -------+-------------------")
for m in range(1, 13):
    cnt = month_resolves.get(m, 0)
    marker = " <---" if m in (7, 8) else ""
    print(f"  {month_names[m]:>5}  |  {cnt:>4}{marker}")

print(f"\n  Total markets:           {len(all_markets)}")
print(f"  Markets resolving ANY:   {sum(month_resolves.values())}")

# ── 6. Try manual parsing of endDate AS Unix timestamp ─────────────────
print("\n" + "=" * 72)
print("WHAT IF endDate IS A UNIX TIMESTAMP? (using fromtimestamp)")
print("=" * 72)

unix_month_resolves = Counter()
for m in all_markets:
    ed = m.get("endDate")
    if ed is None:
        continue
    if isinstance(ed, (int, float)):
        try:
            dt = datetime.fromtimestamp(ed, tz=timezone.utc)
            unix_month_resolves[dt.month] += 1
        except (OSError, ValueError, OverflowError):
            pass

print("  Month  |  Markets resolving (Unix parse)")
print("  -------+---------------------------------")
for m in range(1, 13):
    cnt = unix_month_resolves.get(m, 0)
    marker = " <---" if m in (7, 8) else ""
    print(f"  {month_names[m]:>5}  |  {cnt:>4}{marker}")

# ── 7. Show first few numeric endDate values as datetimes ──────────────
print("\n" + "=" * 72)
print("FIRST 10 NUMERIC endDate VALUES AS DATETIMES")
print("=" * 72)
seen = 0
for m in all_markets:
    ed = m.get("endDate")
    if isinstance(ed, (int, float)):
        try:
            dt = datetime.fromtimestamp(ed, tz=timezone.utc)
            print(f"  id={m.get('id'):>8}  endDate={ed}  ->  {dt.isoformat()}  question={m.get('question','')[:60]}")
            seen += 1
            if seen >= 10:
                break
        except Exception:
            pass

# ── 8. Also show some that ARE resolving correctly ─────────────────────
print("\n" + "=" * 72)
print("MARKETS THAT DO RESOLVE (via current function) - first 10")
print("=" * 72)
seen = 0
for m in all_markets:
    if any(market_resolves_in_month(m, t) for t in range(1, 13)):
        ed = m.get("endDate")
        edi = m.get("endDateIso")
        which_month = [t for t in range(1, 13) if market_resolves_in_month(m, t)][0]
        print(f"  id={m.get('id'):>8}  month={which_month:>2}  endDate={ed!r:>30}  endDateIso={edi!r:>30}  q={m.get('question','')[:60]}")
        seen += 1
        if seen >= 10:
            break

if seen == 0:
    print("  (none)")
