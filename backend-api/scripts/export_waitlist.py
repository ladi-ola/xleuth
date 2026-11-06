"""Private CSV export: DATABASE_URL=... python scripts/export_waitlist.py /secure/path.csv"""

import asyncio
import csv
import os
import sys
from pathlib import Path

import asyncpg


async def main(path: str) -> None:
    repository = Path(__file__).resolve().parents[2]
    if Path(path).resolve().is_relative_to(repository):
        raise ValueError("Choose an export path outside the repository")
    dsn = os.environ["DATABASE_URL"]
    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            "SELECT id, email, name, created_at, consent_at, source "
            "FROM waitlist_entries ORDER BY id"
        )
    finally:
        await conn.close()
    # Exclusive creation; do not overwrite an existing export or expose PII via
    # a world-readable file. Keep output outside the repository.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(("id", "email", "name", "created_at", "consent_at", "source"))
        for row in rows:
            writer.writerow(tuple(row))
    print(f"Exported {len(rows)} entries")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/export_waitlist.py /secure/path.csv")
    asyncio.run(main(sys.argv[1]))
