"""Deeper investigation: look at all markets by endDate month, check year alignment, 
and see if the function misses markets due to subtle format issues."""

import sys, os
from datetime import datetime, timezone
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

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
MAX_PAGES = 3  # 300 markets for better coverage

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

# ── Detailed breakdown by (year, month) from both endDate and endDateIso ──
print("\n" + "=" * 72)
print("DETAILED (YEAR, MONTH) BREAKDOWN FROM endDate")
print("=" * 72)

ym_counter = Counter()
for m in all_markets:
    ed = m.get("endDate")
    if ed and isinstance(ed, str):
        try:
            dt = datetime.fromisoformat(ed.replace("Z", "+00:00"))
            ym_counter[(dt.year, dt.month)] += 1
        except Exception:
            pass

for (y, mo), cnt in sorted(ym_counter.items()):
    marker = " <---" if mo in (7, 8) else ""
    print(f"  {y}-{mo:02d}: {cnt:>4} markets{marker}")

# ── Markets resolving in July ──────────────────────────────────────────
print("\n" + "=" * 72)
print("MARKETS RESOLVING IN JULY (month=7)")
print("=" * 72)
for m in all_markets:
    if market_resolves_in_month(m, 7):
        ed = m.get("endDate")
        edi = m.get("endDateIso")
        print(f"  id={m.get('id'):>8}  endDate={ed!r:>35}  endDateIso={edi!r:>15}  q={m.get('question','')[:80]}")
        print(f"       volume={m.get('volumeNum')}, category={PolymarketClient.get_category(m) if 'PolymarketClient' in dir() else 'N/A'}")

# ── Markets resolving in August ────────────────────────────────────────
print("\n" + "=" * 72)
print("MARKETS RESOLVING IN AUGUST (month=8)")
print("=" * 72)
for m in all_markets:
    if market_resolves_in_month(m, 8):
        ed = m.get("endDate")
        edi = m.get("endDateIso")
        print(f"  id={m.get('id'):>8}  endDate={ed!r:>35}  endDateIso={edi!r:>15}  q={m.get('question','')[:80]}")

if not any(market_resolves_in_month(m, 8) for m in all_markets):
    print("  (none)")

# ── Check ALL endDate values for non-standard formats ──────────────────
print("\n" + "=" * 72)
print("endDate FORMAT CHECK (all 300 markets)")
print("=" * 72)
formats = Counter()
for m in all_markets:
    ed = m.get("endDate")
    if ed is None:
        formats["None"] += 1
    elif isinstance(ed, (int, float)):
        formats["numeric"] += 1
    elif isinstance(ed, str):
        if ed.endswith("Z"):
            if "T" in ed:
                formats["ISO_with_T_and_Z"] += 1
            else:
                formats["Z_no_T"] += 1
        elif "T" in ed:
            formats["ISO_with_T_no_Z"] += 1
        elif "-" in ed:
            formats["date_only"] += 1
        else:
            formats[f"other_str:{ed[:20]}"] += 1
    else:
        formats[f"other_type:{type(ed).__name__}"] += 1

for fmt, cnt in sorted(formats.items()):
    print(f"  {fmt}: {cnt}")

# ── Check: does fromisoformat ever throw on endDate that IS a string? ──
print("\n" + "=" * 72)
print("MANUAL fromisoformat TEST ON endDate")
print("=" * 72)
failures = 0
for m in all_markets:
    ed = m.get("endDate")
    if isinstance(ed, str):
        try:
            dt = datetime.fromisoformat(ed.replace("Z", "+00:00"))
        except Exception as e:
            print(f"  FAIL: id={m.get('id')} endDate={ed!r} error={e}")
            failures += 1
print(f"  Total failures: {failures}")

# ── Check endDateIso format (sometimes it's a date-only string like 2026-07-15) ──
print("\n" + "=" * 72)
print("MARKETS THAT WOULD BE MISSED IF ONLY endDateIso WERE USED")
print("(but found via endDate)")
print("=" * 72)
count_enddate_only = 0
for m in all_markets:
    ed = m.get("endDate")
    edi = m.get("endDateIso")
    if ed and not edi:
        count_enddate_only += 1
        print(f"  id={m.get('id')} endDate={ed!r} (no endDateIso)")
print(f"Total: {count_enddate_only}")

# Also check the reverse
print("\n" + "=" * 72)
print("MARKETS THAT RELY ON endDateIso (no endDate)")
print("=" * 72)
count_iso_only = 0
for m in all_markets:
    ed = m.get("endDate")
    edi = m.get("endDateIso")
    if not ed and edi:
        count_iso_only += 1
        print(f"  id={m.get('id')} endDateIso={edi!r}")
print(f"Total: {count_iso_only}")

# ── Check if there are ANY markets with endDate near Jul/Aug 2026, 2027 ──
print("\n" + "=" * 72)
print("ALL MARKETS WITH endDate IN JULY OR AUGUST (any year, from raw string)")
print("=" * 72)
for m in all_markets:
    ed = m.get("endDate", "")
    if isinstance(ed, str):
        for prefix in ["-07-", "-08-"]:
            if prefix in ed:
                dt = datetime.fromisoformat(ed.replace("Z", "+00:00"))
                print(f"  id={m.get('id'):>8}  {ed!r:>35}  month={dt.month:>2}  year={dt.year}  q={m.get('question','')[:70]}")
                break
