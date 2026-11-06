"""Admin basket CLI: create (dry-run + draft), list/show, register, close/settle, reconcile.

No new HTTP surface (PLAN.md). Wired via Makefile (make basket-*).
DB writes go through xleuth_shared.db_baskets (transitions + immutability
enforced in the data layer). On-chain registration uses web3.py with inline
ABIs and the admin/owner key from env (secret only, never logged).

Index IDs (user decision 2026-10-09, no redeploy):
  legacy rows -> keccak256(canonical NAME), preserved verbatim.
  new rows    -> keccak256(slug).
Registration tx = SettlementEngine.setBasketExpiry(indexId, expiry)
(owner-gated, exists, emits BasketExpiryRegistered). First oracle pushPrice
implicitly creates the price feed; the CLI verifies it but never marks
active before confirmation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv


def _parse_dt(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def _pool():
    import asyncpg

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL is required")
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    from xleuth_shared.db_baskets import ensure_baskets_schema

    await ensure_baskets_schema(pool)
    return pool


async def cmd_create(args) -> int:
    from xleuth_shared.baskets import default_selection_rules, generate_name, make_slug

    rules: dict = {}
    if args.rules_file:
        with open(args.rules_file) as f:
            rules = json.load(f)
    if args.exclude_categories:
        rules["exclude_categories"] = args.exclude_categories
    if not rules:
        rules = default_selection_rules()

    window_start = _parse_dt(args.window_start)
    expiry = _parse_dt(args.expiry)
    # Validation first (refuses on failure, writes nothing on dry-run).
    name = generate_name(args.theme, args.count, expiry)
    slug = make_slug(args.theme, args.count, expiry)

    if args.dry_run:
        from xleuth_admin.selection_runner import dry_run_report

        report = await dry_run_report(
            market_count=args.count, expiry_at=expiry,
            exclude_categories=rules.get("exclude_categories", "sports"),
            selection_rules=rules,
            window_start=window_start,
        )
        print(json.dumps({
            "dry_run": True, "slug": slug, "name": name,
            "theme": args.theme.upper(), "market_count": args.count,
            "window_start": window_start.isoformat(), "expiry_at": expiry.isoformat(),
            **report,
        }, indent=2, default=str))
        return 0

    pool = await _pool()
    try:
        from xleuth_shared.db_baskets import create_draft

        row = await create_draft(
            pool, theme=args.theme, market_count=args.count,
            window_start=window_start, expiry_at=expiry,
            selection_rules=rules, created_by=os.getenv("ADMIN_ACTOR", "cli"),
        )
        print(json.dumps({"draft": row}, indent=2, default=str))
        return 0
    except Exception as e:
        print(f"create failed: {e}", file=sys.stderr)
        return 1
    finally:
        await pool.close()


async def cmd_list(args) -> int:
    pool = await _pool()
    try:
        from xleuth_shared.db_baskets import list_baskets

        rows = await list_baskets(pool, status=args.status)
        print(json.dumps(rows, indent=2, default=str))
        return 0
    finally:
        await pool.close()


async def cmd_show(args) -> int:
    pool = await _pool()
    try:
        from xleuth_shared.db_baskets import get_by_slug

        row = await get_by_slug(pool, args.slug)
        if row is None:
            print(f"unknown slug {args.slug!r}", file=sys.stderr)
            return 1
        print(json.dumps(row, indent=2, default=str))
        return 0
    finally:
        await pool.close()


async def cmd_register(args) -> int:
    """draft -> registering -> active (or registration_failed). Re-runnable."""
    from xleuth_admin.chain import RegistrationChain
    from xleuth_shared.baskets import (
        STATUS_ACTIVE, STATUS_REGISTERING, basket_id_from_slug,
        generate_name, make_slug,
    )

    pool = await _pool()
    try:
        from xleuth_shared.db_baskets import get_by_slug, transition

        row = await get_by_slug(pool, args.slug)
        if row is None:
            print(f"unknown slug {args.slug!r}", file=sys.stderr)
            return 1
        if row["status"] == STATUS_ACTIVE and not args.force:
            print(f"{args.slug} already active ({row.get('onchain_index_id')}); use --force to re-check")
            return 0

        # 1. Validate + re-run selection (live Polymarket, read-only).
        from xleuth_admin.selection_runner import dry_run_report

        exp = row["expiry_at"]
        if hasattr(exp, "month") is False:
            exp = _parse_dt(str(exp))
        canonical_name = generate_name(row["theme"], row["market_count"], exp)
        canonical_slug = make_slug(row["theme"], row["market_count"], exp)
        if row["name"] != canonical_name or row["slug"] != canonical_slug:
            print(
                f"stored identity/expiry mismatch for {args.slug}: expected "
                f"{canonical_name} ({canonical_slug}) from expiry {exp.isoformat()}; "
                "create a corrected draft with a new ID instead of mutating this row",
                file=sys.stderr,
            )
            return 1
        report = await dry_run_report(
            market_count=row["market_count"], expiry_at=exp,
            exclude_categories=(row.get("selection_rules") or {}).get("exclude_categories", "sports"),
            selection_rules=row.get("selection_rules") or {},
            window_start=row["window_start"],
        )
        if report.get("actual_count", 0) == 0:
            print("selection re-run found 0 constituents; refusing to register", file=sys.stderr)
            return 1
        for w in report.get("warnings", []):
            print(f"warning: {w}", file=sys.stderr)
        if not report.get("ready_for_registration", False):
            print("selection/price/live-volume preconditions failed; refusing to register", file=sys.stderr)
            return 1

        # 2. Idempotency: derive index id, check on-chain expiry.
        slug = row["slug"]
        index_id_hex = row.get("onchain_index_id") or ("0x" + basket_id_from_slug(slug).hex())
        chain = RegistrationChain.from_env()
        existing_expiry = chain.get_expiry(index_id_hex)
        intended_expiry = int(exp.timestamp())
        if chain.is_settled(index_id_hex):
            print(f"refusing settled on-chain basket ID {index_id_hex}; settled IDs are immutable", file=sys.stderr)
            return 1
        if existing_expiry and existing_expiry != intended_expiry:
            print(f"refusing expiry mismatch for {index_id_hex}: on-chain={existing_expiry}, requested={intended_expiry}; use a new basket slug", file=sys.stderr)
            return 1
        if existing_expiry and existing_expiry == intended_expiry:
            print(f"on-chain index {index_id_hex} already registered (expiry {existing_expiry}); adopting")
            await transition(pool, slug, STATUS_REGISTERING, actor="cli",
                             payload={"adopted": True, "index_id": index_id_hex})
            await transition(pool, slug, STATUS_ACTIVE, actor="cli",
                             payload={"adopted": True},
                             onchain_index_id=index_id_hex)
            return 0

        # 3. registering + send tx.
        await transition(pool, slug, STATUS_REGISTERING, actor="cli",
                         payload={"index_id": index_id_hex, "expiry": intended_expiry})
        try:
            tx_hash = chain.send_set_expiry(index_id_hex, intended_expiry)
            print(f"sent setBasketExpiry {index_id_hex} expiry={intended_expiry} tx={tx_hash}")
        except Exception as e:
            await transition(pool, slug, "registration_failed", actor="cli",
                             payload={"reason": f"send failed: {e}"})
            print(f"send failed: {e}", file=sys.stderr)
            return 1

        # 4. Wait for confirmations; never mark active before confirmation.
        try:
            receipt_ok = chain.wait_confirmations(
                tx_hash, confirmations=args.confirmations, timeout_s=args.timeout)
        except Exception as e:
            await transition(pool, slug, "registration_failed", actor="cli",
                             payload={"reason": f"confirm timeout: {e}", "tx": tx_hash})
            print(f"confirmation failed: {e} (tx {tx_hash} stored; re-run to retry)", file=sys.stderr)
            # store hash even on timeout path
            async with pool.acquire() as conn:
                await conn.execute("UPDATE baskets SET register_tx_hash=$2 WHERE slug=$1",
                                   slug, tx_hash)
            return 1
        if not receipt_ok:
            await transition(pool, slug, "registration_failed", actor="cli",
                             payload={"reason": "tx reverted", "tx": tx_hash})
            print("tx reverted on-chain", file=sys.stderr)
            return 1

        from datetime import datetime as _dt, timezone as _tz
        await transition(
            pool, slug, STATUS_ACTIVE, actor="cli",
            payload={"tx": tx_hash, "constituents": report.get("actual_count")},
            onchain_index_id=index_id_hex, register_tx_hash=tx_hash,
            registered_at=_dt.now(_tz.utc),
        )
        print(f"{slug} -> active ({index_id_hex})")
        return 0
    finally:
        await pool.close()


async def cmd_close_settle(args, to_status: str) -> int:
    """Wrap existing SettlementEngine/PositionManager flows if they exist.

    TODO: no Python settlement flow exists yet (only contracts/script/
    SettleBasket.s.sol forge script). This stub performs the DB status
    transition + audit event only. Wire the EIP-712 settleBasket relay here.
    """
    pool = await _pool()
    try:
        from xleuth_shared.db_baskets import transition

        row = await transition(pool, args.slug, to_status, actor="cli",
                               payload={"stub": True, "note": "TODO: on-chain settle relay"})
        print(json.dumps(row, indent=2, default=str))
        print(f"TODO: relay on-chain settle for {args.slug} via SettlementEngine.settleBasket",
              file=sys.stderr)
        return 0
    except Exception as e:
        print(f"{to_status} failed: {e}", file=sys.stderr)
        return 1
    finally:
        await pool.close()


async def cmd_reconcile(args) -> int:
    """Compare DB vs on-chain state, report (and optionally repair) drift."""
    from xleuth_admin.chain import RegistrationChain

    pool = await _pool()
    try:
        from xleuth_shared.db_baskets import get_by_slug

        row = await get_by_slug(pool, args.slug)
        if row is None:
            print(f"unknown slug {args.slug!r}", file=sys.stderr)
            return 1
        chain = RegistrationChain.from_env()
        index_id_hex = row.get("onchain_index_id")
        if not index_id_hex:
            print(json.dumps({"slug": args.slug, "drift": "missing onchain_index_id in DB",
                              "status": row["status"]}, indent=2))
            return 1
        onchain_expiry = chain.get_expiry(index_id_hex)
        onchain_price = chain.get_price(index_id_hex)
        db_expiry = int(row["expiry_at"].timestamp())
        drift = []
        if onchain_expiry != db_expiry:
            drift.append(f"expiry db={db_expiry} vs chain={onchain_expiry}")
        report = {"slug": args.slug, "index_id": index_id_hex, "db_status": row["status"],
                  "onchain_expiry": onchain_expiry, "onchain_price": onchain_price,
                  "drift": drift or None}
        print(json.dumps(report, indent=2, default=str))
        if drift and args.repair:
            tx = chain.send_set_expiry(index_id_hex, db_expiry)
            print(f"repair tx: {tx}")
        return 0 if not drift else 2
    finally:
        await pool.close()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="basket", description="Xleuth basket admin CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create", help="dry-run selection or create a draft")
    c.add_argument("--theme", required=True)
    c.add_argument("--count", type=int, required=True)
    c.add_argument("--window-start", required=True, help="ISO UTC, e.g. 2026-10-01T00:00:00Z")
    c.add_argument("--expiry", required=True, help="ISO UTC, e.g. 2026-10-31T23:59:59Z")
    c.add_argument("--rules-file", default=None)
    c.add_argument("--exclude-categories", default=None)
    c.add_argument("--dry-run", action="store_true")
    c.set_defaults(fn=cmd_create)

    l = sub.add_parser("list", help="list baskets")
    l.add_argument("--status", default=None)
    l.set_defaults(fn=cmd_list)

    s = sub.add_parser("show", help="show one basket")
    s.add_argument("slug")
    s.set_defaults(fn=cmd_show)

    r = sub.add_parser("register", help="register a draft on-chain")
    r.add_argument("slug")
    r.add_argument("--confirmations", type=int, default=2)
    r.add_argument("--timeout", type=int, default=300)
    r.add_argument("--force", action="store_true")
    r.set_defaults(fn=cmd_register)

    cl = sub.add_parser("close", help="close an active basket (stub + transition)")
    cl.add_argument("slug")
    cl.set_defaults(fn=lambda a: cmd_close_settle(a, "closed"))

    st = sub.add_parser("settle", help="settle a basket (stub + transition)")
    st.add_argument("slug")
    st.set_defaults(fn=lambda a: cmd_close_settle(a, "settled"))

    rc = sub.add_parser("reconcile", help="compare DB vs on-chain")
    rc.add_argument("slug")
    rc.add_argument("--repair", action="store_true")
    rc.set_defaults(fn=cmd_reconcile)
    return p


def main() -> None:
    load_dotenv()
    args = build_parser().parse_args()
    code = asyncio.run(args.fn(args))
    sys.exit(code or 0)


if __name__ == "__main__":
    main()
