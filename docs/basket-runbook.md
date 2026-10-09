# Basket Runbook (PLAN.md)

Baskets are data (DB `baskets` table), not config. Admin CLI: `make basket-*`
(see `Makefile`). No new HTTP surface. No contract redeploy needed for new
baskets: registration = `SettlementEngine.setBasketExpiry(indexId, expiry)`
(owner tx) + oracle `pushPrice` feed. Live baskets keep `keccak(NAME)` ids;
new baskets use `keccak(slug)`.

## Create -> dry-run -> register -> verify

1. Dry-run selection vs live Polymarket (writes nothing):
   `make basket-create THEME=TOP COUNT=20 WINDOW_START=2026-11-01T00:00:00Z EXPIRY=2026-11-30T23:59:59Z DRY=1`
   Check: resolved constituents, actual vs requested count, total
   volume/liquidity, VWAP preview, warnings (too few liquid markets,
   markets resolving after expiry).
2. Create the draft (refuses on validation failure):
   `make basket-create THEME=TOP COUNT=20 WINDOW_START=... EXPIRY=...`
   Note the printed `slug` (e.g. `top20-2026-11`).
3. Inspect: `make basket-list` / `make basket-show SLUG=top20-2026-11`.
4. Register on-chain (draft -> registering -> active):
   `make basket-register SLUG=top20-2026-11`
   The command re-runs selection, adopts the index if `expiryOf` already
   matches (idempotent, no second tx), else sends `setBasketExpiry`, waits
   for 2 confirmations, then marks `active` with `onchain_index_id` +
   `registered_at`. It never marks active before confirmation.
5. Verify: ingestion picks the basket up next poll (no restart);
   oracle pushes only `active` rows with an `onchain_index_id` and stops
   after expiry; matching rejects orders on non-active; `GET /baskets`
   shows the row with `slug`/`expiry_at`/`onchain_index_id`.

## Recover from failed registration

- Status `registration_failed` + reason in `basket_events`. The tx hash is
  stored when available. The command is re-runnable:
  `make basket-register SLUG=...` (adopts the index if the first tx
  actually mined; otherwise sends a fresh tx).
- Drift check/repair: `make basket-reconcile SLUG=... [REPAIR=1]` compares
  DB (`expiry_at`, status) vs on-chain (`expiryOf`, `latestPrice`,
  `isSettled`) and reports; `REPAIR=1` re-sends `setBasketExpiry`.

## Close / settle

- `make basket-close SLUG=...` / `make basket-settle SLUG=...` perform the
  DB transition today. TODO: wire the `SettlementEngine.settleBasket`
  EIP-712 relay (only the forge script `contracts/script/SettleBasket.s.sol`
  exists so far).

## Month-end rollover

1. In the last week of the month, dry-run next month's basket and create
   the draft. 2. Register it; verify `active` + oracle pushing before the
   1st. 3. The expiring basket stops ingesting/pushing at `expiry_at` and
   stays queryable as history (`closed`/`settled`). 4. Nothing to edit in
   `.env`/compose: `ACTIVE_BASKETS` remains only as a transition fallback
   until the migrated rows are verified, then retired (guardrail
   `make check-baskets` + startup validation fail fast on retired vars).

## Backfill / migration

- `migrations/001_baskets.sql` (reversible via `migrations/down/`).
- Backfill live baskets with preserved ids (no fake prices):
  `PYTHONPATH=infra/scripts:shared python3 infra/scripts/seed_baskets.py --apply`
  (dry-run without `--apply`). Re-running adopts existing rows.
