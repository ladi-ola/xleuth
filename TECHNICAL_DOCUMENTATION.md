# Xleuth — Technical Documentation

> Generated 2026-10-12 from full codebase read (root `/home/lxdiore/Desktop/xleuth`).
> Stack: React 18 SPA + FastAPI `backend-api` + `matching-engine` + `oracle-service` + `data-ingestion` + Postgres/Timescale + Redis + Foundry contracts on Polygon Amoy (chainId 80002, test USDC only).
> Source of truth for basket naming/lifecycle: `shared/xleuth_shared/`.

---

## Table of Contents

1. [Product Overview](#1-product-overview)
2. [Repository Structure](#2-repository-structure)
3. [System Architecture & Data Flows](#3-system-architecture--data-flows)
4. [Technology Stack](#4-technology-stack)
5. [Shared Library (`shared/`)](#5-shared-library-shared)
6. [Data Ingestion (`data-ingestion/`)](#6-data-ingestion-data-ingestion)
7. [Backend API (`backend-api/`)](#7-backend-api-backend-api)
8. [Matching Engine (`matching-engine/`)](#8-matching-engine-matching-engine)
9. [Oracle Service (`oracle-service/`)](#9-oracle-service-oracle-service)
10. [Smart Contracts (`contracts/`)](#10-smart-contracts-contracts)
11. [Admin CLI (`admin-cli/`)](#11-admin-cli-admin-cli)
12. [Frontend (`frontend/`)](#12-frontend-frontend)
13. [Database Schemas](#13-database-schemas)
14. [Auth & Security](#14-auth--security)
15. [Configuration (Env Vars)](#15-configuration-env-vars)
16. [Infra, Migrations, Scripts](#16-infra-migrations-scripts)
17. [Deployment & DevOps](#17-deployment--devops)
18. [Testing](#18-testing)
19. [Docs Directory](#19-docs-directory)
20. [Operational Runbooks](#20-operational-runbooks)
21. [Known Limitations & TODOs](#21-known-limitations--todos)

---

## 1. Product Overview

Xleuth is a **leveraged trading platform for prediction-market index baskets** (testnet only).

- Each **basket/index** (e.g. `TOP20-NOVEMBER`, slug `top20-2026-11`) tracks the **volume-weighted average price (VWAP)** of the top-N Polymarket prediction markets resolving in a target month.
- Users connect an EVM wallet via **Dynamic.xyz**, receive an internal JWT, claim test **MockUSDC** from a faucet, deposit into `CollateralVault`, and trade **long/short leveraged perpetual-like positions** on index prices via the off-chain matching engine, settled on-chain in `PositionManager` + `SettlementEngine`.
- Prices flow: **Polymarket Gamma/CLOB/Data API → data-ingestion → Postgres (`index_prices`) + Redis → backend-api (read) + oracle-service (push to `IndexOracleConsumer`) → matching-engine (margin/mark price) → contracts**.
- Baskets are **data in the `baskets` DB table**, not config. Only `admin-cli/` creates them. No admin HTTP endpoint (enforced by `scripts/check-baskets.sh`).
- Network: **Polygon Amoy testnet only** (`CHAIN_ID=80002`), test funds have no value, data may be reset. See `PLAN.md`, `ADMIN_BASKET_GUIDE.md`, `docs/deployment-status.md`.

Deployed Amoy addresses (see `docs/deployment-status.md`, root `.env`):

| Contract | Address |
|---|---|
| `CollateralVault` | `0x6dbeEb6a5bE0cD63159b1dBD5525dE125A1CECef` |
| `PositionManager` (Week5 `updatePosition`) | `0x65e2687284c64576d2B7Cd55393163Fb9f6871ef` |
| `IndexOracleConsumer` | `0xd394B8A5dace5EB22933A2a0DCE1C82c1Eb70cd2` |
| `SettlementEngine` | `0x68aa3697b1783cb671c575D01C5622c2FA8570e8` |
| `MockUSDC` / `TEST_USDC` | `0xc8783E…` / `0xC12782…` (faucet token) |

Global risk defaults: `MAX_LEVERAGE=5`, `MIN_ORDER_SIZE=10` (USDC notional), `TICK_SIZE=0.01`, `TRADING_FEE_BPS=10` (reporting-only v1), `INDEX_PRICE_SCALE=100` (0–100 points), `ORACLE_MAX_PRICE_STALENESS_SECONDS=60`, `MAINTENANCE_MARGIN_RATIO≈6.25% (625 bps)`, `LIQUIDATION_FEE_BPS=50`.

---

## 2. Repository Structure

```
xleuth/
├── .env                          # root env (git-ignored in prod; local dev secrets — DO NOT COMMIT real keys)
├── .gitignore  .gitmodules
├── README.md                     # repo-structure overview (120 lines, mirrors below)
├── PLAN.md                       # pre-deployment QA plan (19 tasks: privacy/terms/secrets/HTTPS/SEO/perf/UX)
├── ADMIN_BASKET_GUIDE.md         # admin-only basket CLI guide (git-ignored per header)
├── Makefile                      # test/run/basket/deploy targets
├── docker-compose.yml            # postgres+redis+4 python services
├── docs/                         # architecture, api-contract, API_SURFACE, openapi/*.json, runbooks, legal
├── data-ingestion/               # Polymarket → Postgres/Redis poller
├── backend-api/                  # FastAPI :8000 — baskets/accounts/faucet/auth/WS
├── matching-engine/              # FastAPI :8001 — orderbook + margin + settlement
├── oracle-service/               # EIP-712 price pusher loop (15s)
├── contracts/                    # Foundry: Vault/PM/OracleConsumer/SettlementEngine/MockUSDC + scripts/tests
├── shared/                       # xleuth_shared: schemas/baskets/lifecycle/db/auth/rate-limit
├── admin-cli/                    # make basket-* CLI (DB + on-chain register)
├── frontend/                     # React 18 SPA (Fusion Starter) + Express stub
├── infra/scripts/seed_baskets.py # one-off backfill of live baskets
├── migrations/001_baskets.sql    # baskets + basket_events (+ down/)
└── scripts/                      # check-baskets/bundle-secrets/env-examples/links/build-sitemap
```

`README.md:1-120` is the canonical tree (reproduced above with per-file comments). `frontend/AGENTS.md` documents the Fusion Starter template (React Router 6 SPA, Express, pnpm, Vitest, Radix+Tailwind).

---

## 3. System Architecture & Data Flows

### 3.1 Service topology (`docker-compose.yml:1-93`)

| Service | Image/Build | Ports | Depends |
|---|---|---|---|
| `postgres` | `timescale/timescaledb:latest-pg16` | `5432:5432` | — |
| `redis` | `redis:7-alpine` | `6379:6379` | — |
| `data-ingestion` | `data-ingestion/Dockerfile` | none | postgres, redis |
| `backend-api` | `backend-api/Dockerfile` | `${API_PORT:-8000}:8000` | postgres, redis |
| `oracle-service` | `oracle-service/Dockerfile` | none | postgres, redis, data-ingestion |
| `matching-engine` | `matching-engine/Dockerfile` | `${ENGINE_PORT:-8001}:8001` | redis, postgres |

All Python services share `xleuth_net` bridge, `pgdata` volume, root `.env` via `env_file`, plus `DATABASE_URL`/`REDIS_URL` overrides pointing at compose service names.

### 3.2 End-to-end flows

**A. Index computation (every `INGESTION_POLL_INTERVAL_SECONDS=30`):**

```
Polymarket Gamma GET /markets (paginated 100x100, volumeNum desc, closed=false, active=true)
  → select_constituents (month filter + exclude sports + top-N by volumeNum)
  → event_map.build_volume_map: GROUP conditionId BY event_id → 1× GET {DATA}/live-volume?id={eventId} per event (dedup)
  → CLOB POST /midpoints for all clobTokenIds (batch) → per-market _resolve_price (CLOB YES-midpoint else Gamma outcomePrices[0])
  → vwap.basket_vwap([(price,volume)]) = sum(p*v)/sum(v)
  → storage.save_basket → index_prices + market_prices (Timescale hypertables if available)
  → redis_publisher → channel xleuth:basket:{name}:price {basket_name,index_price,scaled_price,computed_at,constituent_count}
```

Single shared market snapshot per cycle (`poller.run_once_items`) feeds all baskets. DB registry (`list_active`) wins; env `ACTIVE_BASKETS` templates fill gaps. Dated baskets never deleted (`cleanup_stale_baskets` regex guard) — history preserved.

**B. Oracle push (every `ORACLE_PUSH_INTERVAL_SECONDS=15`):**

```
Postgres index_prices.scaled_price (fallback Redis xleuth:basket:*:price)
  → signing.price_to_scale (clamp [1,100], round-half-up)
  → signing.sign_price_update (EIP-712 "Xleuth Index Oracle"/"1", PriceUpdate(basketId,price,timestamp))
  → pusher.push_all: skip if (price,ts) == latestPrice on-chain; else pushPrice(basketId,price,ts,sig) gas 200k, retry 5× backoff 2s
```

Only `active` baskets with `onchain_index_id`, stops after `expiry_at`. Basket id: new `keccak256(slug)`; legacy live baskets keep `keccak256(NAME)` — both valid on-chain, no redeploy.

**C. Trading (`POST matching-engine:8001/orders`):**

```
Dynamic JWT → backend POST /auth/verify → internal HS256 JWT (memory, 60m)
  → POST /orders + Authorization: Bearer + Idempotency-Key
  → auth → idempotency replay check (10k cap, 24h TTL)
  → per-type validation (422 codes) → MarginCheck.validate (oracle price, NOT limit price)
  → BasketOrderBook.place/place_market/place_stop/place_sltp
  → SettlementBridge.settle_fills: GROUP legs by (wallet,basket), net, volume-weighted lev → Web3TxSubmitter: pm.updatePosition(basketId,sideEnum,round(|net|),lev) signed by trader EOA key, 300k gas, 120s confirm w/ fee-bump rebroadcast
  → _confirm_fills: BOTH legs must mine else order → REJECTED
  → publish book to Redis xleuth:basket:{basket}:book → backend WS /ws/orderbook relay
  → 201 OrderResponse {order + fills + failed_fills + margin_check}
```

Background trigger loop every 5s: refresh baskets (60s DB poll) + evaluate stop/SL-TP vs oracle mark (`price_int/100`).

**D. Read path (frontend):**

```
Public: GET backend :8000/baskets, /baskets/{name}/price|history|candles|constituents + GET matching :8001/baskets/{name}/book + WS ws://.../ws/price|orderbook/:basket
Authed: GET /accounts/me|alias|transactions|summary + POST /faucet/claim + matching /orders|/positions
```

**E. Settlement at expiry (manual relay v1):**

Off-chain `realized_fraction.compute_realized_fraction` (volume-weighted YES fraction from deduped `volume_map`, resolved `outcomePrices [1,0]→1.0`) → EIP-712 `SettleBasket` signed by settlement signer → any relayer calls `SettlementEngine.settleBasket` (checks expiry, once-only) → `PM.settleBasket` iterates `openUsers` LIFO, `vault.settlePosition(locked,pnl)` per user (`credited=max(locked+pnl,0)`).

---

## 4. Technology Stack

| Layer | Tech | Notes |
|---|---|---|
| Frontend | React 18, React Router 6 SPA, TypeScript, Vite, TailwindCSS 3/4, Radix UI, Lucide, TanStack React-Query, Dynamic.xyz (`@dynamic-labs/*`), `lightweight-charts`, zod, Express stub, pnpm 10.14, Vitest | Fusion Starter template; see `frontend/AGENTS.md`, `package.json` |
| Backend/matching/oracle/ingestion | Python 3.12-slim, FastAPI 0.115, uvicorn, asyncpg, redis-py 5, web3.py 7, eth-account, PyJWT, pydantic 2 + settings, httpx, `order-matching[polars] 0.12` (matching only) | Shared via `shared/xleuth_shared` copied to `/app` in Dockerfiles |
| DB/Cache | TimescaleDB (PG16) + `asyncpg` pool (1–5), Redis 7 | Hypertables optional (`if_not_exists` + extension check) |
| Contracts | Solidity 0.8.24, Foundry, OpenZeppelin (`Ownable, ReentrancyGuard, SafeERC20, ECDSA, EIP712`), EVM paris, optimizer 200 | `foundry.toml`, fuzz 256 (1024 CI) |
| Auth | Dynamic.xyz RS256 JWKS → internal HS256 JWT (`JWT_SECRET`) | No SIWE (stale `SIWE_NONCE_TTL` env unused) |
| Infra | Docker Compose, Netlify (`frontend/netlify.toml`), GitHub Actions (`infra/ci/github-actions.yml` optional) | `Makefile`, `scripts/` guardrails |

---

## 5. Shared Library (`shared/`)

**Path:** `shared/xleuth_shared/` + `shared/requirements.txt` + `shared/tests/`. Single source of truth imported by all Python services (Docker: `COPY shared/xleuth_shared/ /app/xleuth_shared/`, `PYTHONPATH=/app`).

### 5.1 Basket naming (`baskets.py` — THE module)

- `generate_name(theme,count,expiry) → {THEME}{COUNT}-{MONTH}` e.g. `TOP20-NOVEMBER`; `make_slug → {theme}{n}-{yyyy}-{mm}` e.g. `top20-2026-11`.
- `normalize_theme / validate_market_count (>0) / validate_window (expiry>window_start) / validate_transition / assert_mutable_update`.
- `basket_id_from_slug = keccak(slug)` (new); `legacy_basket_id_from_name = keccak(NAME)` (live compat).
- `default_selection_rules {exclude_categories, weighting: vwap, version: 1}`.
- Statuses: `draft → registering → active → closed → settled` (+ `registration_failed`, safely re-runnable). Never `active` before chain confirms (2 confs default).

### 5.2 Lifecycle compat (`basket_lifecycle.py`)

Legacy `ACTIVE_BASKETS` templates (`{MONTH}/<MONTH>/%MONTH%/MONTH OF THE YEAR`, `{YEAR}` substitution, Dec rollover) → `expand_basket_templates(current+next month)` → `active_basket_names()`. `basket_status active|upcoming|resolved`, `is_tradeable(!resolved)`. Used as fallback when DB registry empty.

### 5.3 DB layer (`db_baskets.py`, raw asyncpg)

`BASKETS_TABLE_SQL`, `ensure_baskets_schema()`, `create_draft()`, `get_by_slug()`, `list_baskets()`, `list_active(status=active AND expiry>now)`, `transition(slug,new,+onchain_index_id/register_tx_hash/registered_at/settlement_at/selection_rules)` + `basket_events` audit. Enforces transitions + immutability.

### 5.4 Schemas (`schemas/`)

- `baskets.py`: `ConstituentMarket/SubMarket`, `BasketInfo/Detail(slug,expiry,onchain_index_id)`, `PricePoint`, `BasketPriceResponse(+WithChange 24h)`, `History/List`, `Candle(s)`, `BasketRecord/Create/Event`.
- `orders.py`: `OrderType(limit|market|stop|stop_loss|take_profit)`, `Side`, `Status(open|partially_filled|filled|cancelled|rejected|triggered)`, `RejectionCode` (26 codes), `Limit|Market|Stop|SLTPOrderRequest`, `OrderResponse/Cancel/BookSnapshot/OrderList/Position(s)/PortfolioSummary/Candle`.
- `auth.py`: `DynamicVerifyRequest{token}`, `TokenResponse{access_token,expires_in_minutes}`, `UserInfo`.
- `accounts.py`: `UserInfo`, `TransactionInfo/HistoryResponse`; `faucet.py`: `ClaimRequest{smart_account_address}/Response{tx_hash,status}/Cooldown`; `websocket.py`: `WsPriceUpdate/SubscribeRequest`.

### 5.5 Auth + rate-limit

- `auth/dynamic_jwt.py`: RS256 JWKS verify at `https://app.dynamicauth.com/api/v0/sdk/{env}/.well-known/jwks`, issuer check, wallet from `wallet_address|wallet|address|sub` lowercased, 1h JWKS cache.
- `auth/internal_jwt.py`: HS256 `JWT_SECRET`, `sub→wallet`, errors `token_missing|expired|invalid`.
- `rate_limit.py`: `RateLimitMiddleware(service=...)` sliding-window per-IP: `POST /auth/verify 30/min`, `POST /faucet/claim 10/min`, orders 120/min (env `RL_*_PER_MIN`), `413` if `Content-Length > MAX_BODY_BYTES (1M)`, `429 {detail: rate_limited}+Retry-After`.
- `constants.py`: `INDEX_PRICE_SCALE=100` only. No `abis/` dir — ABIs inline (`oracle pusher.py:ORACLE_ABI`, `admin chain.py:SETTLEMENT_ABI+ORACLE_ABI`).
- Tests: `test_baskets.py`, `test_rate_limit.py` (`PYTHONPATH=shared python3 -m pytest shared/tests/`).

---

## 6. Data Ingestion (`data-ingestion/`)

**Purpose:** Poll Polymarket, compute basket VWAPs, persist to Timescale + publish to Redis. Entrypoint `python -m xleuth_ingestion` → `__main__.py → poller.main()`.

**Files (`src/xleuth_ingestion/`):** `__init__.py` (empty), `__main__.py`, `polymarket_client.py`, `event_map.py`, `selection.py` (replaces spec `liquidity_filter.py` — that file does NOT exist; `MIN_MARKET_*` env dead), `basket_builder.py`, `vwap.py`, `storage.py`, `poller.py`, `realized_fraction.py`, `redis_publisher.py`. Plus `requirements.txt` (httpx, redis, dotenv, asyncpg, pydantic), `Dockerfile` (`PYTHONPATH=/app/src:/app`, `CMD python -m xleuth_ingestion`), `.env.example`, `pytest.ini` (`asyncio_mode=auto`), `diagnose_dates.py/2.py` (endDate vs endDateIso debug), `tests/test_basket_lifecycle.py, test_ingestion_live.py (hits real API), test_realized_fraction.py`.

### 6.1 Config (`poller.load_config`)

`POLYMARKET_GAMMA/CLOB/DATA_API_BASE`, `DATABASE_URL`, `EXCLUDE_CATEGORIES=sports`, `ACTIVE_BASKETS=TOP20-{MONTH}`, `poll_interval=30s`, `REDIS_URL`.

### 6.2 Poll loop (`poller.py:44-208`)

Init `PolymarketClient + Storage + RedisPublisher`; `storage.connect() (asyncpg pool) + ensure_schema()`; loop: `discover_work_items() → run_once_items() → publish_basket() (duplicated twice — bug lines 202-208, harmless double-publish) → cleanup_stale_baskets() (duplicated) → sleep`. Console JSON dump if no DB.

`discover_work_items (:89)`: DB-first — `expand_basket_templates` legacy + `db_baskets.list_active` (`{name,market_count,target_month=expiry_at.month,selection_rules,source=db}`); env fills gaps (skip `RESOLVED`, dedupe). New DB activation picked up next cycle, no restart.

`run_once_items (:138)`: one `_fetch_all_markets()` snapshot shared by all baskets.

### 6.3 Polymarket client (`polymarket_client.py`)

- `get_markets/get_market` (Gamma discovery, paginated `limit&offset&order=volumeNum&ascending=false&closed=false&active=true`, 100×100 max).
- `get_midpoint(token_id) GET {clob}/midpoint?token_id` + `get_midpoints_batch POST {clob}/midpoints` (public, no key).
- `get_live_volume(event_id) GET {data}/live-volume?id=` → `data[0]` (event-scoped; `id` = parent event numeric ID).
- Helpers: `parse_outcomes/parse_outcome_prices/get_volume(volumeNum)/get_category(events[0].category)/get_event_id/get_clob_token_ids`.
- Rule (root `.env:11-20`): Gamma `outcomePrices`/volume cached/reference-only — never feed index or quorum; use CLOB midpoints + live-volume.

### 6.4 Selection (`selection.py`, `basket_builder.py:11-103`, `event_map.py:15`)

- `market_resolves_in_month`: `endDate or endDateIso → fromisoformat(Z→+00:00) → month==target`.
- `select_constituents(markets,count,target_month,exclude)`: pure, no I/O; `target_month=None` disables month filter (custom indexes); category exclude comma-list case-insensitive; `sort(volumeNum desc)[:count] → (top_n, excluded[{id,question,reason}])`.
- `resolve_target_month(expiry_month,rules)`: `rules.target_month` overrides, `null` disables.
- Legacy `build_basket(name)` parses via `parse_basket_name → (n,month)` e.g. `TOP20-AUGUST=(20,8)` — DEPRECATED; new `build_basket_from_params(name,client,count,target_month,exclude,rules,markets)`.
- `build_volume_map(markets,client)`: group `conditionId` by `event_id`, one `/live-volume` per event (dedup, `0x`-normalize lowercase, sum `entry.value` per `conditionId`); tolerates `HTTPError`; proven no double-count when 2 constituents share event.
- `_resolve_price`: `yes_token=clob_token_map[cond][0] → midpoint_map[yes]` else any token → fallback `outcomePrices[0]` (`source=clob|gamma_fallback`).
- Output dict: `{basket_name,computed_at UTC,index_price,index_price_scaled=round(price*100,2),total_constituents,markets_filtered_out,excluded_markets,constituents[{market_id(id or conditionId),condition_id,clob_token_id,event_id,question,end_date,price,volume(map.get(cond,volumeNum)),price_source}]}`; only `price is not None` enters VWAP.

### 6.5 VWAP + realized fraction (`vwap.py`, `realized_fraction.py:50`)

- `basket_vwap([(price,volume)])` + `sub_outcome_vwap` (identical alias, unused): skip `volume<=0`, `sum(p*v)/sum(v)`, `None` if total≤0.
- `compute_realized_fraction(constituents,volume_map)`: settlement = volume-weighted YES fraction; `_outcome_yes_price`: resolved `[1,0]→1.0`, `[0,1]→0.0`, else `0.0` (eps 1e-9); MUST use deduped `volume_map`, never raw `volumeNum`; skips missing/zero-vol.

### 6.6 Storage (`storage.py:9-102`)

`index_prices(ts,basket_name,index_price,scaled_price,constituent_count,constituents JSONB)`; `market_prices(ts,market_id,basket_name,question,price,volume,event_id)`; `ensure_schema` splits `BASE_TABLE_SQL` + `db_baskets.BASKETS_TABLE_SQL` + `create_hypertable(...,if_not_exists)` if `pg_extension=timescaledb`. `save_basket` = `_save_index_price + _save_market_prices` in separate txns. `cleanup_stale_baskets(active)`: `DELETE WHERE basket_name != ALL($1) AND basket_name !~ '^[A-Z]+[0-9]+-[A-Z]+(-[0-9]{4})?$'` — dated baskets never deleted.

`redis_publisher.py`: channel `xleuth:basket:{name}:price`, payload `{basket_name,index_price,scaled_price,computed_at,constituent_count}`; disabled if no `REDIS_URL`.

---

## 7. Backend API (`backend-api/`)

**Entrypoint:** `src/xleuth_api/main.py → create_app() → app`. Docker `CMD uvicorn xleuth_api.main:app --host 0.0.0.0 --port ${PORT:-8000}`.

**Files:** `__init__.py` (empty), `main.py`, `db.py`, `dependencies.py`, `chain.py`, `auth/__init__.py + auth/dynamic_jwt.py` (thin wrapper over shared), `models/__init__.py` (EMPTY — models live in `shared/schemas/`), `routes/__init__.py` (empty), `routes/auth.py, baskets.py, accounts.py, faucet.py, websocket.py`. `requirements.txt` (fastapi 0.115, uvicorn, asyncpg, redis 5, web3 7, eth-account, PyJWT, cryptography, requests, pydantic 2, httpx, pytest-asyncio), `Dockerfile`, `.env.example`, `tests/conftest.py, test_auth_flow.py, test_faucet_auth.py, test_websocket.py, test_tasks_15_16.py`.

### 7.1 App wiring (`main.py:24-117`)

- `lifespan`: `db.connect()+ensure_schema()` else `Running without database persistence`; `aioredis.from_url(redis://host:port/db)+ping()` else `redis=None → WebSocket degraded`; shutdown closes both.
- `create_app`: `CORSMiddleware(origins=CORS_ALLOWED_ORIGINS split comma, allow_credentials, *methods/headers)` + `RateLimitMiddleware(service="backend-api")`; state: `db=Database(dsn)`, `dynamic_auth_handler=DynamicAuthHandler(env_id, jwt_secret, expiry, jwks_ttl)`, `chain_reader=Web3ChainStateReader(chain_config) if rpc_url else None`, `redis=None`; routers: `auth, baskets, accounts, faucet, websocket`.

### 7.2 Endpoints

**Auth (`routes/auth.py`, `prefix=/auth`):**

| Method | Path | Purpose | Guard |
|---|---|---|---|
| POST | `/auth/verify` | Verify Dynamic JWT (`{token}`) → `upsert_user` → issue internal HS256 (`{access_token,token_type=Bearer,expires_in_minutes}`) | public, 30/min/IP |
| GET | `/auth/me` | Return `UserInfo` for bearer holder | internal JWT |

**Accounts (`routes/accounts.py`, `prefix=/accounts`, all internal-JWT):**

| Method | Path | Purpose |
|---|---|---|
| GET | `/accounts/me` | Fresh `db.get_user` else token stub → `UserInfo` |
| PUT | `/accounts/alias?alias=` | Validate + `update_user_alias`; Task15: 1–32 chars, `^[A-Za-z0-9 _.\-]+$`, else 422 |
| GET | `/accounts/transactions?limit=50` | `get_transactions → TransactionHistoryResponse` |
| GET | `/accounts/summary` | `vault_free=chain.free_balance/1e6`, `wallet_balance=chain.wallet_balance/1e6` → `PortfolioSummaryResponse{total=vault_free+wallet_balance,free_margin=vault_free,used=0,unrealized=0,realized=0}`; zeros if `chain_reader is None`. Only `vault_free` is tradeable margin. |

**Baskets (public, no auth, `routes/baskets.py`, `prefix=/baskets`):**

| Method | Path | Purpose |
|---|---|---|
| GET | `/baskets` | DB-first (`list_basket_records + get_latest_basket_price`) else DISTINCT scan; each + 24h change |
| GET | `/baskets/{name}/price` | Latest `index_prices` + registry `slug/expiry/onchain_index_id` + 24h change |
| GET | `/baskets/{name}/history?start&end&limit≤10000` | `PricePoint[]` DESC |
| GET | `/baskets/{name}/constituents` | Latest constituents JSON + `BasketDetail` |
| GET | `/baskets/{name}/candles?interval&limit&start&end` | Timescale `time_bucket` OHLC; `1m,5m,15m,30m,1h,4h,1d,1w` |

Lifecycle (`:30-51`): DB `status/expiry_at` wins if registry row exists (`active+unexpired→active/tradeable`, `closed/settled/expired→non-tradeable`), else name-derived `basket_status()/is_tradeable()`.

**Faucet (`routes/faucet.py`, `prefix=/faucet`):**

`POST /faucet/claim` — transfer 1,000 test-USDC (6dp) via operator key on Amoy. Body `{smart_account_address}` → `{tx_hash,status=submitted}`. Guards: internal JWT (401 `token_missing`); 400 bad EVM format; 403 if `address != wallet`; 429 if <24h since last claim + `Retry-After`; 500 if env/RPC fails; 10/min/IP. `AsyncWeb3` transfer, gas×1.2 buffer, sign+send (`:117-136`).

The faucet only delivers USDC to the user's wallet. Trading margin is `CollateralVault.freeBalance`, so the frontend's Portfolio page has a separate **Deposit to vault** action that signs `USDC.approve(vault, amount)` followed by `vault.deposit(amount)` with the user's connected wallet (`frontend/client/lib/contracts.ts`). The helper reads `balanceOf(wallet)` on-chain for the amount, so a stale summary cannot over- or under-deposit. The backend never holds user keys.

**WebSocket (`routes/websocket.py`, no auth):**

- `WS /ws/price/{basket}` — Redis `xleuth:basket:{basket}:price` relay; fallback DB poll 5s (`POLL_INTERVAL=5.0`).
- `WS /ws/orderbook/{basket}` — Redis `xleuth:basket:{basket}:book` (matching depth); idle loop if no Redis.
- Shared `_client_loop`: `ping→pong`, `subscribe+basket_name→subscribed`, else `error Invalid message format`.

### 7.3 DB (`db.py`, asyncpg pool min1/max5, graceful no-DB mode)

`users(wallet PK,alias,balance,realized/unrealized_pnl,created_at)`; `transactions(id,wallet FK,tx_type,amount,tx_hash,timestamp,related_position_id)` + idx; `faucet_claims(wallet PK,last_claim_at)`; + `db_baskets` registry. Methods: basket reads (`get_basket_record/list_basket_records/get_latest/get_history/get_constituents/list_baskets/get_price_24h_ago/get_candles(time_bucket)`), user (`upsert/get/update_alias/get_transactions/add`), faucet (`get_last/record`).

Read-only chain (`chain.py:17-45`): `free_balance→vault.freeBalance`, `get_position→pm.getPosition(side,size,entry,lev,locked)`, `oracle_price→latestPrice`, `max_leverage`. `Web3ChainStateReader` uses `keccak(text=basket_name)`.

### 7.4 Dependencies/middleware

`dependencies.py:19-33`: `HTTPBearer(auto_error=False)`; `get_current_user`: missing→401 `token_missing`; `internal_verifier.verify_token` (401 `e.code`); `get_user` else stub `{wallet,alias None,balance 0,…}`. `get_db/get_auth_handler/get_chain_reader`. `CORSMiddleware + RateLimitMiddleware`.

---

## 8. Matching Engine (`matching-engine/`)

**Entrypoint:** `src/xleuth_matching/main.py` (`load_dotenv`, `app=create_app() if _env_ready() else None`, `SystemExit` if env missing) → `uvicorn xleuth_matching.main:app --host 0.0.0.0 --port 8001`. Single-instance FastAPI (serialized placement/cancel, no distributed lock).

**Files:** `__init__.py`, `config.py`, `orderbook.py` (868 lines), `margin_check.py` (326), `settlement.py` (309), `api.py` (934, `Engine` class), `main.py`, `basket_source.py`. `requirements.txt` (+ `order-matching[polars] 0.12`), `Dockerfile`, `.env.example` (37 lines), `tests/test_orderbook.py (167), test_margin_check.py (183), test_settlement.py (159), test_api.py (1131, TestClient+FakeChain/FakeSubmitter), test_matching_live.py (309 Amoy), test_e2e_live.py (564 Week-6 full E2E)`.

### 8.1 Config (`config.py:138`)

Frozen dataclass: `rpc_url, vault/PM/oracle addresses, jwt_secret, chain_id, price_scale, max_leverage, min_order_size, tick_size, fee_bps, staleness, baskets, redis_url, trader_keys{wallet→privkey}, cors, host/port`. `load()`: `POLYGON_AMOY_RPC_URL|RPC_URL` required; `_addr` auto-`0x`; `JWT_SECRET` (must match backend); `CHAIN_ID=80002, SCALE=100, MAXLEV=5, MINSIZE=10, TICK=0.01, FEE=10bps, STALENESS=60`; `ACTIVE_BASKETS=TOP20-{MONTH} → active_basket_names()`; `CORS=localhost:8080,3000`; `ENGINE_HOST/PORT, REDIS_URL`; `_trader_keys` scans `TRADER\d*_PRIVATE_KEY → Account.from_key().address.lower→key` (trader EOA signs own `updatePosition`); `RETIRED_BASKET_ENV_VARS` guardrail.

### 8.2 Orderbook (`orderbook.py`)

Built on `order-matching==0.12.0` (`MatchingEngine(seed)`, `unprocessed_orders`, `Orders([Order])`, `match(ts)→ExecutedTrades`) + metadata, self-trade guard, depth.

Types: `Status open|partially_filled|filled|cancelled|rejected|triggered`; `Type limit|market|stop|stop_loss|take_profit`; `Side buy/sell`; `OrderRecord{order_id,basket,trader,side,price,size,leverage,type,max_slippage_bps,trigger_price,position_id,oco_group_id,status,filled,rejection,created_at}` (`remaining`, `rest()=open|partial`); `Fill{trade_id,basket,price,size,ts,taker/maker,trader,side,leverage}` (`notional`, fee stub reporting-only); `PlacementResult{order,fills,error}`, `SelfTradeError`.

`BasketOrderBook(seed=1)` (`_engine/_book/_orders + _stop_orders + _sltp_orders + _oco_groups`):

- `place(limit)`: self-trade guard → `engine.place → match → _apply_trade` (both sides filled/OPEN→PARTIAL→FILLED) → `Fill`s at resting price. GTC, price-time priority.
- `place_market(FOK+slippage)`: `0≤slip≤10000`; depth `best_bid/ask`; `worst=ask*(1+bps/1e4)` buy / `bid*(1-bps/1e4)` sell; `no_liquidity` if empty; `insufficient_liquidity` if `sum(size within worst)<size`; self-trade guard → walk sorted levels ≤worst (crossing LIMIT each), `FILLED` else `fok_failed`+rollback. Multi-level walk.
- `place_stop(GTC)`: `trigger>0`, stored (not in book). `check_triggers(mark)`: `BUY mark≥trigger, SELL mark≤trigger → MARKET (preserve slip/trigger) → TRIGGERED+filled or REJECTED`.
- `place_sltp(OCO full-close)`: require `position_id,trigger>0`; no extra margin (locked). `check_sltp_triggers`: `SL: SELL(mark≤trig)|BUY(mark≥trig)` (close long/short); `TP: SELL(mark≥trig)|BUY(mark≤trig)` → market → `TRIGGERED` + sibling `CANCELLED (oco_cancelled)` else `REJECTED`.
- `cancel(id)`: regular→engine `CANCEL+match`; pending stop/sltp→pop→`CANCELLED` (stash for query); sibling OCO cancel; `FILLED/CANCELLED/REJECTED/TRIGGERED→ValueError`, unknown→`KeyError`.
- `snapshot()/depth(20)`: aggregated `(price,size)` best-first; `best_bid/ask,mid,spread,ts`. `OrderBookManager{name:book}` lazy-create, `names()` sorted.

### 8.3 Margin (`margin_check.py`)

`CheckResult{ok,reason,details}`, `ChainState` ABC (`oracle_price(basket,hex)→(price,ts)|None, free_balance, max_leverage, position_size, get_position`). `Web3ChainState`: ABIs `oracle.latestPrice(b32)→(price,ts)`, `vault.freeBalance`, `pm.maxLeverage/getPosition`; `basket_id=hex|keccak(text)` preferring DB `index_ids`; try/except→`None/0`.

`MarginCheck.validate(basket,wallet,side,price|None,size,leverage)`:
1. Static: basket (registry non-empty: membership+`expiry>now`+`active`; else `config.baskets+is_tradeable`), `size≥MIN`, `1≤lev≤MAX`, price only if given: `0<price≤100` + on-tick `|round(p/tick)-p/tick|≤1e-6`.
2. Oracle: `None→oracle_unreadable`, `≤0→oracle_price_zero`, `ts==0 or now-ts>max→oracle_price_stale{age,max}`.
3. `maxLeverage≤0→leverage_cap_unreadable`, `lev>cap→leverage_above_cap`.
4. Margin: `required=(oracle_price_int*size)/leverage` (oracle, not limit — matches `PositionManager` lock), `free/1e6`; `free<required→insufficient_margin{required,free,oracle_price,size,leverage}` else `ok`.

### 8.4 Settlement (`settlement.py:309`)

`PositionUpdate{wallet,basket,side,size,leverage; size_int=round(size)}`, `Outcome{update,ok,tx_hash,error,mined_at}`, `SIDE_TO_ENUM{BUY:0 Long,SELL:1 Short}`, `ALERTS=xleuth:engine:alerts`, `CONFIRM_TIMEOUT=120s`. `TxSubmitter.submit(update)→(hash,receipt)`. `Web3TxSubmitter`: lookup `trader_keys[wallet]` else `no private key`; `basket_id` via DB map; `pm.updatePosition(basketId,sideEnum,size_int,leverage)`; gas 300k, `maxPriority 30gwei`, `maxFee=base*factor+tip`; send→wait 2s poll, rebroadcast bump ×1.5 ≤3 if dropped; timeout→`TimeoutError`. `SettlementBridge.settle_fills`: `_group` legs per `(wallet,basket)` skipping untracked (warn); `net=sum(+buy/-sell)`; `|net|<1e-9→skip net-zero`, `round(|net|)==0→skip dust`; `side=BUY if net>0`, `lev=vol-weighted mean round(max1)`; per update `submit→receipt.status!=1→REVERT+alert`; exception→`FAILED+alert`; success→`ok+mined_at`. Never raises. `api._confirm_fills`: confirmed only if BOTH taker+maker `ok`; else both →`REJECTED: settlement failed`.

### 8.5 API (`api.py:934`, `Engine`)

Auth `HTTPBearer(auto_error=False) → internal_verifier.verify_token → wallet`; missing→401 `token_missing`. All except `GET /baskets/{}/book` require wallet; cancel/get enforce `order.trader==wallet` else 403/404. `CORS + RateLimitMiddleware(matching-engine)`, Redis alerts. Trigger loop: `_trigger_evaluation_loop` every 5s (`STOP_TRIGGER_CHECK_INTERVAL=5`): `refresh_baskets (ENGINE_BASKET_REFRESH=60)` + `_evaluate_all_triggers` (oracle `price_int/100` → `check_triggers+check_sltp` → settle+publish). `basket_source.py`: DB-first registry 60s TTL (`ENGINE_BASKET_CACHE_TTL_S`), `index_ids_from_rows name→onchain_id`; empty→env fallback; `attach_registry` wires `margin.registry/index_ids, chain._index_ids`, creates books on-demand.

| Method | Path | Purpose |
|---|---|---|
| POST | `/orders →201 OrderResponse` | `OrderRequest{basket,side?,size?>0,leverage?≥1,type=LIMIT,price?>0,slip 0-10000,trigger?>0,position_id?,oco?}`. Per-type 422: LIMIT needs side/size/lev/price; MARKET/STOP needs side/size/lev/slip≠0 (+trigger for STOP); SL/TP needs trigger/slip≠0/position_id + `_get_position_from_chain` else `position_not_found`; client side/size/lev must match derived else `sl_tp_field_mismatch` (overwrite full-close). Margin: SL/TP→fake ok; else `validate(price=None for market/stop)`; fail→STOP/SLTP `201 REJECTED`, LIMIT/MARKET→422. Place→`REJECTED+publish` on error else settle→confirm→publish→idempotency→response |
| DELETE | `/orders/{id} →CancelResponse` | Find across books, ownership, `cancel()`, 409 if `ValueError`, publish |
| GET | `/orders/{id} →OrderResponse` | Ownership-checked (no fills history) |
| GET | `/baskets/{basket}/book →BookSnapshot` (unauth) | 404 if unknown; `{basket,bids[{price,size}],asks,best/mid/spread,ts}` |
| GET | `/orders?status=open\|history\|all&basket&limit≤200&cursor →OrderList` | Collect `_orders+_stop+_sltp` for wallet, filter, `created desc`, cursor pagination (`older than cursor_id`), `avg_fill:null` |
| GET | `/positions →PositionsResponse` | Per `known_basket`: `chain.get_position` + oracle mark (`/100`) + direct `pm.getPosition` for `entry/locked` (fallback `mark*size/lev`) → `unrealized=(mark-entry)*size`, `%`, SL/TP from resting orders, `{position_id=wallet_basket,…,liquidation:null,fee:null,opened_at:now}` |

Schemas from `xleuth_shared.schemas.orders`. Idempotency: in-memory `(wallet,key)→(order_id,expiry)`, TTL 86400s, cap 10k.

---

## 9. Oracle Service (`oracle-service/`)

**Purpose:** Loop every 15s: DB-first price read → scale/round → EIP-712 sign → `pushPrice`. Only `active` + `onchain_index_id`, stops after expiry.

**Files:** `src/xleuth_oracle/price_source.py, signing.py, pusher.py, basket_source.py, config.py, main.py, __main__.py`, `requirements.txt` (web3, eth-account, eth-utils, asyncpg, redis, pytest), `Dockerfile`, `pytest.ini`, `.env.example`, `tests/test_signing.py, test_config.py`.

- `price_source.py`: `PostgresPriceSource(SELECT scaled_price FROM index_prices WHERE basket_name ORDER BY ts DESC)` + `RedisPriceSource(GET xleuth:basket:{name}:price→scaled_price)` + `Composite(Postgres→Redis→None)`.
- `signing.py`: `basket_id_from_name=keccak(name)`, `sign_price_update(PriceUpdate(basketId,price,timestamp), domain "Xleuth Index Oracle"/"1")→65B r‖s‖v`, `sign_settle_basket(SettleBasket…, "Xleuth Settlement"/"1")`, `price_to_scale(float,100)=clamp[1,100] round-half-up`.
- `pusher.py`: inline `ORACLE_ABI{pushPrice,latestPrice}`, `connect(Web3.HTTPProvider+ExtraDataToPOAMiddleware)`, `latest_onchain_price()`, `current_timestamp(block)`, `_send(sign→build_tx gas200k→send→wait 120s)`, `push_all(prices,index_ids)+_push_with_retry(exp backoff, skip if (price,ts) identical)`.
- `basket_source.py`: `discover_baskets(config,pool)`: `list_active` (TTL 60s `ORACLE_BASKET_CACHE_TTL_S`) + env fallback with `_legacy_id=keccak(name)`; `[{name,index_id,expiry,source:db|env}]`.
- `config.py`: `OracleConfig.load()` — `POLYGON_AMOY_RPC_URL|RPC_URL|ORACLE_RPC_URL`, `INDEX_ORACLE_CONSUMER_ADDRESS`, `ORACLE_SIGNER_PRIVATE_KEY|DEPLOYER_PRIVATE_KEY`, `CHAIN_ID=80002`, `DATABASE_URL`, `REDIS_URL`, `ACTIVE_BASKETS`, `SCALE=100`, `PUSH_INTERVAL=15`, `STALENESS=60`, `RETRY_MAX=5`, `RETRY_BACKOFF=2`, `CACHE_TTL=60`, `LOG_LEVEL`; `signer_address=Account.from_key(key).address`.
- `main.py`: `run_cycle(discover→scaled→push_all)+loop_forever(push-on-boot then sleep)`, SIGINT/SIGTERM.

---

## 10. Smart Contracts (`contracts/`)

**Toolchain:** `foundry.toml` (`src/out/libs=[lib] test/script`, solc 0.8.24, paris, optimizer 200, fuzz 256/1024 CI, gas reports Vault/PM/Oracle/MockUSDC, fmt 100). `lib/` (OZ etc. via `forge install`), `broadcast/cache/out/`, `README.md`, `.env/.env.example` (47 lines: chain 80002, RPC, deployer key, deployed addrs, `TEST_USDC`, oracle/settlement signer keys fallback deployer, `MAX_LEVERAGE=5, STALENESS=60, SCALE=100, MAINT_BPS=625, LIQ_FEE_BPS=50, SETTLE_STALENESS=3600, BASKET_EXPIRY=0, ACTIVE_BASKETS, BASKET_INITIAL_PRICES=50`).

**Sources (`src/`):** `CollateralVault.sol`, `PositionManager.sol`, `IndexOracleConsumer.sol`, `SettlementEngine.sol`, `MockUSDC.sol`.

### 10.1 `CollateralVault.sol` (`Ownable+ReentrancyGuard`, `SafeERC20`)

State: `IERC20 immutable collateralToken`; `address positionManager` (sole operator); `freeBalance/lockedBalance[user]`.
- `constructor(token,owner)` — revert `ZeroAddress` if 0.
- `setPositionManager(addr) onlyOwner` (migratable).
- `deposit(amount) nonReentrant`: `safeTransferFrom`, `free+=`; `InvalidAmount` if 0.
- `withdraw(amount)`: only `free`, never locked; `InsufficientFreeBalance`.
- `lockMargin(user,amount) onlyPM`: `free-=,locked+=`.
- `releaseMargin(user,amount) onlyPM`: `locked-=,free+=`.
- `settlePosition(user,lockedAmount,pnl:int256) onlyPM`: `locked-=locked`; `total=locked+pnl`; `credited=max(total,0)→free` (loss floored, shortfall absorbed by platform). Units `(settled-entry)*size`.
- `liquidatePosition(user,liquidator,locked,pnl,fee) onlyPM`: consume all `locked`, `equity=max(locked+pnl,0)`, `paid=min(fee,equity)→liquidator.free`, remainder→`user.free`.
- Views `totalCollateral→token.balanceOf(this)`, `balanceOf→free+locked`.
- Errors `NotPositionManager/InsufficientFree|Locked/InvalidAmount/ZeroAddress`; events `Deposit/Withdraw/MarginLocked/Released/PositionSettled(lockedReleased,credited)/Liquidated(user,liquidator,locked,equity,reward)/PositionManagerSet`.

### 10.2 `IndexOracleConsumer.sol` (`Ownable+EIP712("Xleuth Index Oracle","1")`)

State: `priceScale` immutable (100); `authorizedOracle` (single MVP signer); `maxStaleness`; `latestPrice[b32]→{price,timestamp}`; `PRICE_TYPE="PriceUpdate(bytes32 basketId,uint256 price,uint256 timestamp)"`.
- `pushPrice(basketId,price,ts,sig)` permissionless relay: (1) `ts ≤ last.ts →StaleUpdate` (monotonic); (2) `ts+maxStaleness<block.ts →StaleUpdate`; (3) `price==0||>scale →PriceOutOfRange`; (4) `recover(_hashTypedDataV4…) != oracle →UnauthorizedSigner`; store + `PriceUpdated(basketId,price,ts,signer)`.
- `setAuthorizedOracle/setMaxStaleness onlyOwner`; `priceOf(b32)→(price,ts)`; `latestPrice` getter. No freshness check — enforced by PM.

### 10.3 `PositionManager.sol` (`Ownable`, immutable `vault+oracle`)

State: `maxLeverage`, `maxStaleness`, `maintenanceMarginRatioBps` (625), `liquidationFeeBps` (50), `settlementEngine`; `enum Side{Long,Short}`; `Position{side,size,entryPrice,leverage,lockedMargin}`; `positions[user][basket]` (one net position/user/basket); `openUsers[basket]→address[]` + `openUserIndex` (O(1) swap-remove, drives settlement enumeration).
- Admin `onlyOwner`: `setMaxLeverage(≠0)/setMaxStaleness/setMaintenance(≠0)/setLiquidationFee/setSettlementEngine(≠0)`.
- `openPosition(basket,side,size,lev)`: `ZeroSize/InvalidLeverage(>max)/PositionExists`; `_requireFreshPrice` (exists `≠0`, `block.ts ≤ updated+staleness`, `≠0` else `PriceNotFresh/ZeroPrice`); `margin=price*size/lev` (`InvalidPrice` if 0); `vault.lockMargin`; push `openUsers`; `PositionOpened`.
- `updatePosition(basket,side,size,lev)` (Week5 matching): fresh price; none→`_openInternal`; same side→`_increaseInternal` (lock `price*size/lev`, size-weighted `newEntry=(old*oldSize+price*size)/newSize`, lev avg, `PositionIncreased`); opposite→`_flattenInternal`: full close if `size≥posSize` (delete, remove, `vault.settlePosition(locked,pnl)`, `PositionSettled+Closed`, remainder opens opposite); partial (`size<pos`): `lockedPortion=locked*size/pos`, `portionPnl=pnl*size/pos`, shrink, `vault.settlePosition`, `PositionDecreased`.
- `closePosition(basket)`: full close, `vault.releaseMargin` (no PnL — Settlement milestone handles PnL), `PositionClosed`; `NoOpenPosition` if none.
- `liquidate(user,basket)` permissionless: `NoOpenPosition` if none; fresh price; `notional=price*size`; `pnl=(price-entry)*size` (negated Short); `equity=max(locked+pnl,0)`; liquidatable iff `equity*1e4 < notional*maintBps` (strictly below; equality NOT) else `NotLiquidatable`; `reward=notional*feeBps/1e4`; delete+remove, `vault.liquidatePosition(…,reward)`, `PositionLiquidated(liquidator,user,…reward)+Closed`.
- `settleBasket(basket,settleValue) only settlementEngine (NotSettlementEngine)`, `ZeroPrice` if 0: `while(users.length>0)` pop-from-end, skip+remove empties, `pnl` vs `settleValue`, `credited=max(locked+pnl,0)`, delete+remove, `vault.settlePosition`, `PositionSettled+Closed` per user.
- Views `getPosition/getOpenUserAt/getOpenUserCount/equityOf(locked+pnl floored, live oracle w/o staleness)`.
- Events `PositionOpened/Increased/Decreased/Closed/Settled(price,pnl,credited)/Liquidated + MaxLeverage/Staleness/Maintenance/Fee/SettlementEngineSet`.

### 10.4 `SettlementEngine.sol` (`Ownable+EIP712("Xleuth Settlement","1")`)

State: `PM immutable`; `authorizedSigner` (single realized-fraction signer); `priceScale` (100); `maxSettlementStaleness`; `expiryOf[basket]`; `isSettled[basket]`; `SETTLE_TYPE="SettleBasket(bytes32 basketId,uint256 realizedPrice,uint256 timestamp)"`.
- `settleBasket(basket,realized,ts,sig)` any relayer: (1) `expiry==0→UnknownBasket`; `isSettled→AlreadySettled`; `block.ts<expiry→NotExpired` (inclusive); (2) `realized==0||>scale→InvalidFraction`; (3) `ts+maxStale<block.ts→StaleSignature`; (4) `recover != signer→Unauthorized`; (5) `isSettled=true; PM.settleBasket(basket,realized)` (EVERY open position at realized volume-weighted YES fraction from deduped live volume, NOT Gamma); `BasketSettled(basket,price,ts,signer,relayer)`. Once-only.
- Admin `onlyOwner`: `setBasketExpiry/setAuthorizedSigner(≠0)/setMaxSettlementStaleness`; events `BasketExpiryRegistered/AuthorizedSignerSet/MaxSettlementStalenessSet`.

### 10.5 `MockUSDC.sol`

`ERC20+Ownable`, 6 decimals, `mint(to,amount) onlyOwner`, testnet-only.

### 10.6 Scripts (`script/`)

- `DeployAmoy.s.sol`: full Week3+4 — resolve USDC (deploy `MockUSDC` if `TEST_USDC` empty); `vault(owner=deployer) → oracle(owner, signer=ORACLE||deployer, scale, staleness) → PM(owner,vault,oracle,maxLev,staleness,maintBps,feeBps) → vault.setPositionManager(PM) → SettlementEngine(owner,PM,signer||deployer,scale,settleStaleness)` + optional `setBasketExpiry` per `ACTIVE_BASKETS` if `EXPIRY_SECS≠0` → `PM.setSettlementEngine`; logs addrs.
- `DeployMockUSDC.s.sol`: `MockUSDC("Test USD Coin","USDC")` owner=deployer.
- `DeploySettlementEngine.s.sol`: vs existing Week5 PM; deploy engine, `PM.setSettlementEngine`, optional expiries.
- `ConfigureBaskets.s.sol`: seeds oracle — expand `ACTIVE_BASKETS` month templates (current+next, `{YEAR}`, Dec rollover) or literal; prices default 50 or `BASKET_INITIAL_PRICES`; EIP-712 `PriceUpdate` signed by oracle||deployer, `pushPrice` per basket.
- `SettleBasket.s.sol`: manual — optional `setBasketExpiry(NAME,SECS)` then `settleBasket(NAME,REALIZED)` with `SettleBasket` sig (`timestamp=block.timestamp`).
- `OpenPosition.s.sol`: demo long — `mint→approve(vault)→deposit(AMOUNT)` then `openPosition(NAME,Long,SIZE,LEV)` as `TRADER||deployer`.
- `RedeployCore.s.sol` (Week4 vault+PM; old vault can't gain settle/liquidate; reuses USDC+oracle; optional engine `REGISTER_ENGINE=1`).
- `RedeployWeek5.s.sol` (fresh vault+PM with `updatePosition`; reuses USDC+oracle; old positions/deposits lost — Amoy-acceptable).
- `UpgradeAmoy.s.sol` (gas-lean: reuse vault+oracle, fresh PM+engine, `vault.setPositionManager(newPM)`, `PM.setSettlementEngine`, optional expiries).
- `MintMockUSDCReserve.s.sol`: owner mints fixed `10M*1e6` to `OPERATOR_WALLET_ADDRESS`.
- Helpers `_envPrivateKey` (tolerates missing `0x`), `_split/_substring` comma-split.

**Tests (`test/`):** `CollateralVault.t.sol, PositionManager.t.sol, IndexOracleConsumer.t.sol, SettlementEngine.t.sol, ConfigureBaskets.t.sol, OracleServiceCrossCheck.t.sol` (`forge test --gas-report`).

---

## 11. Admin CLI (`admin-cli/`)

**Purpose:** `make basket-*` wrapper — `create(dry-run|draft)/list/show/register/close/settle/reconcile`. DB via `shared.db_baskets`, chain via `web3.py` owner key. No HTTP surface (PLAN constraint). Full guide: `ADMIN_BASKET_GUIDE.md`.

**Files:** `src/xleuth_admin/cli.py, chain.py, selection_runner.py`, `tests/test_basket_flows.py`, `requirements.txt`.

- `cli.py`: `create(--theme --count --window-start --expiry --rules-file --exclude-categories --dry-run)→dry_run_report|create_draft`; `list/show`; `register(slug --confirmations 2 --timeout 300 --force)`: re-run selection→refuse 0 constituents→derive `keccak(slug)`→`get_expiry` adopt-if-match else `send_set_expiry→wait_confirmations→registering→active`; `close/settle` (DB-only stub, TODO `settleBasket` relay, prints reminder); `reconcile(--repair)` compares `expiry/db vs expiryOf/latestPrice/isSettled` (exit 0 sync, 2 drift).
  - Validation: `THEME 1–16 [A-Z0-9]`, `COUNT>0`, `EXPIRY>WINDOW_START` (ISO UTC `Z`). Slug exists→`already exists` (no dup).
- `chain.py`: `RegistrationChain(rpc,settlement,oracle,admin_key,chain_id)` — `SETTLEMENT_ABI{expiryOf,isSettled,setBasketExpiry}`, `ORACLE_ABI{latestPrice}`, `from_env()`, `get_expiry/get_price/send_set_expiry/wait_confirmations`. Key from env, never logged.
- `selection_runner.py`: `dry_run_report` — live `_fetch_all_markets→select→volume_map→_resolve_price→vwap → {actual_count,total_volume,vwap_preview,excluded_count,constituents,warnings}`.
- Env: `DATABASE_URL`, `POLYGON_AMOY_RPC_URL|RPC_URL`, `SETTLEMENT_ENGINE_ADDRESS`, `INDEX_ORACLE_CONSUMER_ADDRESS`, `ADMIN_PRIVATE_KEY|DEPLOYER_PRIVATE_KEY`, `CHAIN_ID=80002`, `ADMIN_ACTOR=cli`.
- Makefile: `ADMIN_PY=PYTHONPATH=admin-cli/src:data-ingestion/src:shared python3 -m xleuth_admin.cli`; `basket-create/list/show/register/close/settle/reconcile`.

---

## 12. Frontend (`frontend/`)

**Template:** Fusion Starter per `frontend/AGENTS.md` — React 18 + React Router 6 SPA + TS + Vite + Tailwind 3 + Express integrated (single port 8080 dev, hot reload, `/api/*`), pnpm, Vitest, Radix+Lucide. Rule: only create Express endpoint when strictly necessary (private keys, DB).

**Structure (`frontend/`):** `client/ (pages, components/ui, components/xleuth, lib/api, App.tsx, global.css)`, `server/ (index.ts stub, routes/demo.ts, node-build.ts)`, `shared/api.ts` (`DemoResponse` leftover), `public/`, `index.html`, `vite.config.ts/server.ts`, `tailwind.config.ts`, `components.json`, `netlify.toml`, `.env/.env.example`, `package.json` (`fusion-starter`, scripts `dev/build/build:client/build:server/start/typecheck/test`), `MANUAL_E2E.md`, `AGENTS.md`.

**Routes (`client/App.tsx`):** `/, /market/:slug →Markets` (main trade view), `/explore →Explore`, `/portfolio`, `/account`, `/how-it-works`, `/legal-risk-disclosure`, `/support`, `/privacy`, `/terms`, `* →NotFound`. Wrappers: `DynamicContextProvider(EthereumWalletConnectors) + QueryClientProvider + RouteTracker(pageview) + CookieNotice + ErrorBoundary`.

**Pages:** `Markets.tsx, Explore.tsx, Portfolio.tsx, Account.tsx, InfoPage.tsx, NotFound.tsx, Support.tsx, Privacy.tsx, Terms.tsx, HowItWorks.tsx, LegalRiskDisclosure.tsx`.

**API layers:**

- `lib/api/backend.ts` — `backendApi.{verifyToken,getBaskets,getBasketPrice,getBasketHistory,getBasketConstituents,getCandles,getAccount,updateAlias,getTransactions,getSummary,claimFaucet}` + `backendWs.{getPriceWsUrl→/ws/price/:name, getOrderBookWsUrl→/ws/orderbook/:name}`.
- `lib/api/matching.ts` — `matchingApi.{placeOrder(+Idempotency-Key),getOrders(status/basket/limit/cursor),getOrder,cancelOrder,getOrderBook→/baskets/:name/book,getPositions→/positions}`.
- `lib/api/hooks.ts` — `useBaskets/useBasketPrice(s)/useBasketHistory/useBasketConstituents/useCandles/useOrderBook` (public) + `useAccount/usePortfolioSummary/useTransactions/usePositions/useOpenOrders/useOrderHistory` (gated on Dynamic `user`) + `usePlaceOrder/useCancelOrder/useFaucetClaim` (optimistic rollback, no auto-retry on ambiguous POST).
- `lib/api/token-exchange.ts` — `exchangeDynamicToken(): getAuthToken()→POST /auth/verify→cache HS256 in-memory +1min buffer`, `authenticatedFetch(fn)` with 401 retry, `clearInternalToken()`.
- `lib/api/urls.ts` — `secureUrl()`: upgrade `http/ws→https/wss` when page HTTPS. `schemas.ts, adapters.ts (adaptBasket/adaptCandles/adaptOrderBook/buildMarketOrder), queryKeys.ts, errors.ts (ApiError), ws-client.ts, polling.spec.ts`.
- `lib/dynamic.ts` — `DYNAMIC_ENVIRONMENT_ID`, `XLEUTH_CHAIN{id:80002}`, placeholder contract addrs. `lib/market-data.ts, portfolio-data.ts, analytics.ts (cookieless pageview)`, `components/xleuth/{Layout,TopBar,BottomNav,SideMenu,IndexHeader,PriceChart,OrderBook,TradeModal,TradeButtons,OrderResultModal,PositionCard,OpenOrderCard,HistoryCard,SignInSheet,…}` + `components/ui/*` (Radix).
- `server/index.ts` stub: only `GET /api/ping, /api/demo`.

**Env (`VITE_*`, public by design):** `VITE_DYNAMIC_ENVIRONMENT_ID`, `VITE_BACKEND_API_URL=http://localhost:8000`, `VITE_MATCHING_ENGINE_URL=http://localhost:8001`, `VITE_BACKEND_WS_URL=ws://localhost:8000`, `VITE_MATCHING_WS_URL`, `VITE_CHAIN_ID=80002`, `VITE_CHAIN_NAME/RPC_URL`, `VITE_COLLATERAL_TOKEN_ADDRESS=0xc8783E…`, `VITE_COLLATERAL_VAULT_ADDRESS=0x6dbeEb…`, `VITE_USDC_CONTRACT_ADDRESS` (legacy alias), `VITE_FAUCET_WALLET_ADDRESS`, `VITE_ROBOTS_CONTENT=noindex,nofollow`, `VITE_PUBLIC_SITE_URL=https://xleuth.xyz`, `VITE_ANALYTICS_URL/SITE`.

**Flows:** Dynamic SDK JWT → `POST {BACKEND}/auth/verify` → internal JWT (memory) → `Authorization: Bearer` to `:8000/accounts|faucet`, `:8001/orders|positions`. Public `GET /baskets…/candles + :8001/…/book`. WS with `ping/subscribe`. Funding: `Portfolio → Get test USDC` (faucet → wallet) then `Portfolio → Deposit to vault` (`approve` + `vault.deposit` signed by the user's wallet). Trade: `Markets → buildMarketOrder(notional,price,lev,slipBps) → POST /orders + Idempotency-Key → toast/reconcile via GET /orders`.

**PLAN.md frontend tasks (1,2,5-19):** privacy/terms pages + docs, secrets audit (public `VITE_*` justified, domain-restrict WalletConnect/RPC, disable prod sourcemaps, bundle secret check), HTTPS/HSTS/CSP, cookie notice (cookieless analytics default), meta/OG/favicon/robots/sitemap (noindex testnet default, env-flag flip), alt-text lint, WebP, Lighthouse, 404/500, link checks, form validation, Turnstile+honeypot+rate limits, Plausible/Umami analytics (no wallet/balance in events), single CTA "Launch app (testnet)".

---

## 13. Database Schemas

**Postgres/Timescale (`docker-compose: postgres`). All `IF NOT EXISTS` for concurrent boot.**

| Table | Columns | Created by |
|---|---|---|
| `index_prices` | `ts TIMESTAMPTZ, basket_name TEXT, index_price DOUBLE, scaled_price DOUBLE, constituent_count INT, constituents JSONB` (+ hypertable) | `data-ingestion/storage.py:9-33` |
| `market_prices` | `ts, market_id TEXT, basket_name TEXT, question TEXT, price DOUBLE, volume DOUBLE, event_id TEXT` (+ hypertable) | same |
| `baskets` | `id SERIAL PK, slug UNIQUE, name, theme, market_count>0, window_start, expiry_at>window_start, settlement_at, selection_rules JSONB{} , status draft\|registering\|active\|closed\|settled\|registration_failed, onchain_index_id, register_tx_hash, registered_at, created/updated_at, created_by, uq(theme,count,expiry)` + idx status/basket | `migrations/001_baskets.sql` + `shared/db_baskets.py` |
| `basket_events` | `basket_id FK→baskets, event, actor, payload, created_at` | same |
| `users` | `wallet_address PK, alias, balance DOUBLE 0, realized/unrealized_pnl 0, created_at` | `backend-api/db.py:10-36` |
| `transactions` | `id PK, wallet FK, tx_type, amount, tx_hash, timestamp, related_position_id` + idx wallet | same |
| `faucet_claims` | `wallet_address PK, last_claim_at` | same |

Rollback: `migrations/down/001_baskets.down.sql` (`DROP basket_events, baskets`).

**Redis keys/channels:** `xleuth:basket:{name}:price` (ingestion→backend WS/oracle fallback), `xleuth:basket:{name}:book` (matching→backend WS), `xleuth:engine:alerts` (settlement failures). JWKS cache 1h (in-memory), basket-registry cache 60s (oracle/matching), idempotency map in-memory (10k/24h).

---

## 14. Auth & Security

- **No SIWE.** Grep confirms: only `faucet.py:112` eth-tx `nonce` + stale `SIWE_NONCE_TTL_SECONDS` env. Actual: **Dynamic.xyz → internal JWT** (see §7/§8).
  - `shared/auth/dynamic_jwt.py:78-119`: RS256 JWKS (`https://app.dynamicauth.com/api/v0/sdk/{env}/.well-known/jwks`), issuer check, wallet lowercased.
  - `shared/auth/internal_jwt.py:41-68` + `backend-api/auth/dynamic_jwt.py:20-56`: HS256 `JWT_SECRET`, `{sub:wallet,iat,exp=60m}`, errors `token_missing|expired|invalid`.
  - `backend-api/dependencies.py`: `HTTPBearer(auto_error=False)`, stub user if DB miss.
  - Frontend caches internal JWT in-memory (+1min buffer), 401-retry, `clearInternalToken()` on logout.
- **Faucet guards:** JWT-bound (403 cross-wallet), 24h cooldown (429+`Retry-After`), EVM-format 400, 10/min/IP.
- **Alias validation (Task15):** 1–32 chars, `^[A-Za-z0-9 _.\-]+$`, 422 + safe messages; tests in `test_tasks_15_16.py`.
- **Rate limiting (Task16, `shared/rate_limit.py`):** per-IP sliding window, `429 rate_limited+Retry-After`, `413` >1MB, `TRUST_PROXY=0` default. Tunables `RL_AUTH_VERIFY_PER_MIN=30, RL_FAUCET_PER_MIN=10, RL_ORDERS_PER_MIN, MAX_BODY_BYTES`.
- **Trading guards:** margin on oracle price, staleness 60s, tick 0.01, min order notional 10 USDC, lev 1–5 + on-chain cap, self-trade reject, FOK+slippage, OCO SL/TP, idempotency keys, ownership checks (403), both-legs-mined confirmation.
- **Contracts:** `onlyOwner` wiring, `onlyPM` margin moves, `only settlementEngine` for `settleBasket`, `ReentrancyGuard` on deposit, monotonic + range + EIP-712 sig checks, once-only settlement, loss floored at 0.
- **Operational (PLAN tasks 3-4):** secrets audit (proxy secrets, rotate if ever in git/bundle, `VITE_*` allowlist, disable sourcemaps, `check-bundle-secrets.sh`), HTTPS 301/HSTS/mixed-content/`wss`, secure cookies, CORS https-only, CSP/`X-Content-Type-Options`/`Referrer-Policy`/frame protections, `curl` verify. See `docs/security-review.md`, `deployment-https.md`.

---

## 15. Configuration (Env Vars)

**Root `.env` is local/dev-only — never commit real keys (values redacted here). Per-service `.env.example` are templates; `scripts/check-env-examples.sh` (`make check-secrets`) enforces drift.**

| Area | Vars |
|---|---|
| General | `APP_NAME=xleuth, APP_ENV=development\|staging\|production, LOG_LEVEL=INFO` |
| Polymarket | `POLYMARKET_GAMMA_API_BASE=https://gamma-api.polymarket.com, POLYMARKET_CLOB_API_BASE=https://clob.polymarket.com, POLYMARKET_DATA_API_BASE=https://data-api.polymarket.com` |
| Index | `EXCLUDE_CATEGORIES=sports, ACTIVE_BASKETS=TOP20-{MONTH}, BASKET_SIZE_DEFAULT=20, INGESTION_POLL_INTERVAL_SECONDS=30, INDEX_PRICE_SCALE=100` |
| DB/Redis | `POSTGRES_HOST/PORT/DB/USER/PASSWORD, DATABASE_URL, REDIS_HOST/PORT/DB/URL` (compose overrides to service names) |
| API/Auth | `API_HOST/PORT, JWT_SECRET (shared backend↔matching), JWT_EXPIRY_MINUTES=60, CORS_ALLOWED_ORIGINS (prod: https, no wildcard+creds), DYNAMIC_ENVIRONMENT_ID, DYNAMIC_JWKS_CACHE_TTL=3600` |
| Chain | `CHAIN_ID=80002, POLYGON_AMOY_RPC_URL (or RPC_URL/ORACLE_RPC_URL), COLLATERAL_VAULT_ADDRESS, POSITION_MANAGER_ADDRESS, INDEX_ORACLE_CONSUMER_ADDRESS, SETTLEMENT_ENGINE_ADDRESS, TEST_USDC_ADDRESS, MOCK_USDC_ADDRESS, DEPLOYER_PRIVATE_KEY (secret), OPERATOR_WALLET_ADDRESS/PRIVATE_KEY (faucet secret), ORACLE_SIGNER_PRIVATE_KEY (secret), SETTLEMENT_SIGNER_PRIVATE_KEY (secret), TRADER_PRIVATE_KEY(+TRADER2_…) (secret, scanned TRADER\d*)` |
| Faucet | `FAUCET_AMOUNT=1000*1e6 (code const)` |
| Oracle | `ORACLE_PUSH_INTERVAL_SECONDS=15, ORACLE_MAX_PRICE_STALENESS_SECONDS=60, ORACLE_RETRY_MAX_ATTEMPTS=5, ORACLE_RETRY_BACKOFF_SECONDS=2, ORACLE_BASKET_CACHE_TTL_S=60` |
| Risk/matching | `MAX_LEVERAGE=5, MAINTENANCE_MARGIN_RATIO=0.0625 (625bps), LIQUIDATION_FEE_BPS=50, TRADING_FEE_BPS=10, MIN_ORDER_SIZE=10, TICK_SIZE=0.01, ENGINE_HOST/PORT, ENGINE_BASKET_REFRESH_SECONDS=60, ENGINE_BASKET_CACHE_TTL_S=60, STOP_TRIGGER_CHECK_INTERVAL_SECONDS=5, IDEMPOTENCY_TTL_SECONDS=86400` |
| Deploy/infra | `DOCKER_NETWORK=xleuth_net, FRONTEND_ORIGIN, BASKET_EXPIRY_SECONDS=0, BASKET_INITIAL_PRICES=50, ACTIVE_BASKETS` |
| Frontend (`VITE_*` public) | `VITE_DYNAMIC_ENVIRONMENT_ID, VITE_BACKEND_API_URL, VITE_MATCHING_ENGINE_URL, VITE_BACKEND_WS_URL, VITE_MATCHING_WS_URL, VITE_CHAIN_ID=80002, VITE_CHAIN_NAME/RPC_URL, VITE_COLLATERAL_TOKEN_ADDRESS, VITE_COLLATERAL_VAULT_ADDRESS, VITE_USDC_CONTRACT_ADDRESS (legacy alias), VITE_FAUCET_WALLET_ADDRESS, VITE_ROBOTS_CONTENT=noindex,nofollow, VITE_PUBLIC_SITE_URL, VITE_ANALYTICS_URL/SITE` |
| Contracts deploy | `CHAIN_ID, RPC_URL, DEPLOYER_PRIVATE_KEY, *_ADDRESS, TEST_USDC_ADDRESS, ORACLE/SIGNER keys, MAX_LEVERAGE/STALENESS/SCALE/MAINT_BPS/FEE_BPS/SETTLE_STALENESS, ACTIVE_BASKETS, BASKET_INITIAL_PRICES, CHAIN_ID` |

---

## 16. Infra, Migrations, Scripts

- `infra/scripts/seed_baskets.py`: idempotent backfill via `create_draft/transition` (no fake prices). `ACTIVE_BASKETS→active_basket_names→parse→month_bounds→make_slug + legacy keccak(NAME)`; dry-run prints plan, `--apply` writes `draft→registering→active`. Env `DATABASE_URL, ACTIVE_BASKETS, EXCLUDE_CATEGORIES`. Rollback `migrations/down/001_baskets.down.sql`.
- `infra/docker/`, `infra/ci/github-actions.yml` (test-on-push, optional).
- `migrations/001_baskets.sql` + `down/001_baskets.down.sql` (see §13).
- `scripts/`: `check-baskets.sh` (fails on hardcoded `TOP{N}-{MONTH}`, literal month `ACTIVE_BASKETS`, or `parse_basket_name/extract_target_month` outside `basket_lifecycle|basket_builder|poller|test`), `check-bundle-secrets.sh` (`make check-bundle`), `check-env-examples.sh` (`make check-secrets`, pre-commit via `make install-hooks`), `check-links.sh` (`make check-links`), `build-sitemap.sh`. No `scripts/dev.sh` (README reference absent).

---

## 17. Deployment & DevOps

**Docker Compose (`docker-compose.yml`):** `docker compose up -d / down` (`make up/down`). Each Python service builds from root context with its `Dockerfile` (`python:3.12-slim, pip install requirements, COPY src + shared, PYTHONPATH=/app, CMD uvicorn/python -m …`).

**Makefile targets:**

| Group | Targets |
|---|---|
| Tests | `test (ingestion), test-contracts (forge --gas-report), test-api, test-oracle, test-matching (excl. live E2E), test-e2e (live Polymarket→Amoy, once per basket), test-all, test-shared` |
| Baskets | `basket-create (THEME COUNT WINDOW_START EXPIRY [DRY=1] [RULES=rules.json]), basket-list ([STATUS]), basket-show (SLUG), basket-register ([CONFIRMATIONS=2] [TIMEOUT=300] [FORCE=1]), basket-close/settle/reconcile ([REPAIR=1])` |
| Run | `run-ingestion (python -m xleuth_ingestion), run-api (uvicorn :8000 --reload), run-oracle, run-matching (:8001)` |
| Contracts | `deploy-testnet (DeployAmoy --rpc-url $RPC_URL --private-key $DEPLOYER --broadcast), deploy-upgrade (UpgradeAmoy), deploy-config-baskets, deploy-settle-basket, deploy-open-position` (all read `contracts/.env`, never hardcode) |
| Checks | `check-secrets, check-baskets, check-bundle, check-links, install-hooks (pre-commit)` |

**Contracts deploy:** `cd contracts && forge script … --rpc-url $(grep '^RPC_URL=' .env|cut -d= -f2) --private-key $(grep '^DEPLOYER_PRIVATE_KEY=' .env|cut -d= -f2) --broadcast` (see §10.6 for script matrix).

**Frontend deploy:** `pnpm build` (`build:client/build:server`), `pnpm start`, `typecheck`, Netlify (`netlify.toml`). Production checks per PLAN: `npm run build` + preview, `curl` HTML (no-JS meta), `curl` domain (HTTPS/HSTS/404/redirects), Lighthouse mobile+desktop, link crawl, smoke (landing/legal/404/connect/trade/logout, no console errors/mixed content). Rollback: revert frontend/proxy (see PLAN cross-cutting).

---

## 18. Testing

| Suite | Command | Coverage |
|---|---|---|
| Ingestion | `PYTHONPATH=data-ingestion/src:shared pytest data-ingestion/tests/ -v` | `test_ingestion_live (real API), test_basket_lifecycle, test_realized_fraction (dedup proof)` |
| Backend | `PYTHONPATH=backend-api/src:shared pytest backend-api/tests/ -v` | `test_auth_flow (MockDynamic handler, 401 codes), test_faucet_auth (401/403/400), test_websocket (ping/subscribe), test_tasks_15_16 (alias 422, rate-limit 429, 413)` |
| Matching unit | `PYTHONPATH=matching-engine/src:shared pytest matching-engine/tests/ -v --ignore=test_e2e_live.py` | `test_orderbook (price-time, FOK, triggers, OCO, cancel), test_margin_check (183 lines), test_settlement (159), test_api (1131, FakeChain/Submitter)` |
| E2E live | `PYTHONPATH=data-ingestion/src:oracle-service/src:matching-engine/src:shared pytest matching-engine/tests/test_e2e_live.py -v -s` | Week-6: Polymarket→VWAP→oracle→match→expiry→settle+payout (real Amoy, dedicated basket, run once) + `test_matching_live (309 Amoy)` |
| Oracle | `PYTHONPATH=oracle-service/src:shared pytest oracle-service/tests/ -v` | `test_signing, test_config` |
| Contracts | `cd contracts && forge test --gas-report` | `CollateralVault/PositionManager/OracleConsumer/SettlementEngine/ConfigureBaskets/OracleCrossCheck` |
| Shared | `PYTHONPATH=shared pytest shared/tests/ -v` | `test_baskets, test_rate_limit` |
| Admin | `admin-cli/tests/test_basket_flows.py` | CLI flows |
| Frontend | `pnpm test (vitest), typecheck` | `polling.spec.ts`, etc. |

`make test-all = test + test-contracts + test-api + test-oracle + test-matching + test-shared`.

---

## 19. Docs Directory

| File | Purpose |
|---|---|
| `architecture.md` | 6-week MVP master plan (Python/FastAPI/Timescale/Redis, off-chain match + on-chain custody, single-key oracle, Amoy+MockUSDC, baskets as DB data) |
| `architecturev1.1.md` | v1.1 live-data ingestion notes |
| `api-contract.md` + `API_SURFACE.md` + `openapi/xleuth-api.json, xleuth-matching.json` | Plain-English + OpenAPI for `:8000/baskets|auth|accounts|faucet|ws` + `:8001/orders|book|positions`; validation (tick/min/lev/slip/trigger/position, Idempotency-Key, 120/min, 422 codes), oracle-price margin, `confirmed=true` only if mined |
| `basket-runbook.md` | `make basket-*`, rollover, backfill |
| `deployment-status.md` | Live Amoy addrs, `:8000/:8001` + ingestion/oracle(15s)/PG/redis, Week-6 E2E pass |
| `deployment-https.md` | HTTPS/HSTS/CSP runbook |
| `analytics.md` | Cookieless (Plausible/Umami), events: pageview, CTA, connect started/completed, first deposit/order; never wallet/sig/balance |
| `programmatic-seo.md` | Basket pages only if real DB data; else ship nothing |
| `security-review.md` | Week 6 self-review |
| `privacy-policy.md` + `terms.md` | Source for `/privacy`, `/terms` (placeholders `[[FILL: operator/contact/jurisdiction/date]]`) |

Plus root `PLAN.md` (19 QA tasks), `ADMIN_BASKET_GUIDE.md` (admin CLI).

---

## 20. Operational Runbooks

**Create/register basket (admin only, `ADMIN_BASKET_GUIDE.md`):**

```bash
python3 -m xleuth_admin.cli --help            # or make basket-list
make basket-create THEME=TOP COUNT=20 WINDOW_START=2026-11-01T00:00:00Z EXPIRY=2026-11-30T23:59:59Z DRY=1 [RULES=rules.json]
# read actual_count/volume/VWAP/warnings; 0 constituents → stop
make basket-create THEME=TOP COUNT=20 WINDOW_START=... EXPIRY=...   # → slug e.g. top20-2026-11
make basket-list && make basket-show SLUG=top20-2026-11            # draft check
make basket-register SLUG=top20-2026-11 [CONFIRMATIONS=3] [TIMEOUT=600] [FORCE=1]
# re-runs selection → keccak(slug) → expiryOf adopt-if-match else setBasketExpiry → 2 confs → active
make basket-show SLUG=...                                          # active + onchain_index_id
make basket-reconcile SLUG=... [REPAIR=1]                          # 0 sync, 2 drift
make basket-close SLUG=... && make basket-settle SLUG=...          # DB-only today + on-chain TODO reminder
```

`rules.json`: `{exclude_categories: "sports", weighting: "vwap", target_month: 11|null}`. Month-end rollover: last week dry-run next month → create → register → confirm `active`+pushing before 1st; expiring basket auto-stops at `expiry_at`, stays as history. Backfill: `PYTHONPATH=infra/scripts:shared python3 infra/scripts/seed_baskets.py [--apply]`.

**Failure table:** `DATABASE_URL required → export`; `slug exists → show`; `0 constituents → fix dates/count`; `confirmation failed → re-run (adopts if mined)`; `reverted → check SETTLEMENT_ENGINE_ADDRESS+key`; `unknown slug → list`; `retired env var → unset (baskets in DB)`.

---

## 21. Known Limitations & TODOs

- `data-ingestion/poller.py:202-208`: duplicated `publish_basket` + `cleanup_stale_baskets` calls (harmless, cleanup).
- `liquidity_filter.py` + `MIN_MARKET_*` filter do not exist (spec drift; `selection.py` is the real filter).
- `backend-api/models/__init__.py` empty (models in `shared/schemas/` by design); stale `SIWE_NONCE_TTL_SECONDS` env; `accounts/summary` simplified (used=0, unrealized=0 — on-chain PnL in matching `/positions`).
- `close/settle` CLI is DB-only; on-chain `settleBasket` relay TODO (only `SettleBasket.s.sol` forge script exists).
- Single-key oracle/settlement signer (MVP trust assumption); no `abis/` dir (inline ABIs); `TRADING_FEE_BPS` reporting-only; `liquidation:null, fee:null, avg_fill:null` placeholders in API.
- `scripts/dev.sh` referenced in README but absent.
- PLAN pre-deploy gates still open: placeholders `[[FILL:…]]` in legal pages, secret rotation if ever committed, DNS/provider dashboards (WalletConnect allowlist, Turnstile, analytics), `noindex→index` flip, mainnet risk language, restricted jurisdictions/governing law.

---

*End of technical documentation. For procedure, see `ADMIN_BASKET_GUIDE.md`; for QA gates, see `PLAN.md`; for live status, see `docs/deployment-status.md`.*
