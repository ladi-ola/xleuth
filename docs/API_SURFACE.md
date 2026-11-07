# Xleuth API Surface

> **2026-11-06:** The HTTP endpoint shapes below are still legacy. The staged
> [V2 signed-execution protocol](relayed-execution-v2.md) is not yet exposed by
> `POST /orders`. New DB basket ingestion uses year-qualified half-open
> resolution windows, Data API v2 taker-share volume (no Gamma-volume fallback),
> and up to 3-decimal index-point prices. Do not send V2 signatures to the
> legacy endpoint or treat the legacy settlement path as repaired.

Generated from FastAPI OpenAPI specs. This document describes all public HTTP endpoints for the backend API (port 8000) and matching engine (port 8001).

**Base URLs (local/dev):**
- Backend API: `http://localhost:8000`
- Matching Engine: `http://localhost:8001`

**Authentication:**
- All authenticated endpoints require `Authorization: Bearer <internal_jwt>`
- Internal JWT is obtained via `POST /auth/verify` with a Dynamic.xyz JWT
- Token `sub` claim = wallet address (lowercased)
- Machine-readable 401 codes: `token_missing`, `token_expired`, `token_invalid`
- 403 used only for "authenticated but not the owner"

---

## Backend API (Port 8000)

### Waitlist (Public)

`POST /waitlist` — body `{ "name": "Ada Lovelace", "email": "ada@example.com", "website": "" }`.
Name is whitespace-normalized (1–100 characters after trimming); email is trimmed and lowercased. `website` is a honeypot and must be left empty. New, duplicate and honeypot submissions return the same `201` response: `{ "status": "ok" }`. Invalid input returns `422`; per-IP throttling returns `429` with `Retry-After`; unavailable storage returns `503`. No public listing endpoint exists. Postgres is the source of truth; Dynamic contact sync is disabled pending a supported waitlist API.

---

### Auth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/verify` | No | Exchange Dynamic JWT for internal HS256 JWT |
| GET | `/auth/me` | Yes | Get current user profile |

**`POST /auth/verify`**  
Request: `{ "token": "<dynamic_jwt>" }`  
Response: `{ "access_token": "<hs256_jwt>", "token_type": "Bearer", "expires_in_minutes": 60 }`  
Errors: 401 `token_invalid` (invalid Dynamic JWT)

**`GET /auth/me`**  
Response: `UserInfo` — wallet_address, alias, balance, realized_pnl, unrealized_pnl, created_at

---

### Baskets (Public)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/baskets` | List all baskets with latest price, status, 24h change |
| GET | `/baskets/{basket_name}/price` | Latest index price + 24h change |
| GET | `/baskets/{basket_name}/history` | Time series of computed prices |
| GET | `/baskets/{basket_name}/constituents` | Constituent Polymarket markets |
| GET | `/baskets/{basket_name}/candles` | OHLC candles (TimescaleDB time_bucket) |

**Basket naming:** `TOP{N}-{MONTH}` (e.g., `TOP20-SEPTEMBER`) or `TOP{N}-{MONTH}-{YEAR}` (e.g., `TOP20-JANUARY-2027`).  
Status: `active` | `upcoming` | `resolved`. `is_tradeable` = true only for active baskets before expiry.

**`GET /baskets`**  
Query: none  
Response: `BasketListResponse` — array of baskets with:
- `basket_name`, `total_constituents`, `index_price`, `index_price_scaled`, `computed_at`, `status`, `is_tradeable`
- `change_24h_abs` (nullable), `change_24h_pct` (nullable) — computed from price nearest 24h ago

**`GET /baskets/{basket_name}/price`**  
Response: `BasketPriceResponseWithChange` — same fields as list item plus `constituent_count`

**`GET /baskets/{basket_name}/history`**  
Query: `start` (ISO8601), `end` (ISO8601), `limit` (default 1000, max 10000)  
Response: `BasketHistoryResponse` — `basket_name`, `prices[]` (ts, index_price, scaled_price, constituent_count), newest last

**`GET /baskets/{basket_name}/constituents`**  
Response: `BasketDetail` — basket info + `constituents[]` (condition_id, clob_token_id, event_id, question, end_date, price, volume, price_source, sub_markets[], sub_market_count, market_id)

**`GET /baskets/{basket_name}/candles`**  
Query: `interval` (1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w), `limit` (default 200, max 10000), `start`, `end` (optional ISO8601)  
Response: `CandlesResponse` — `basket_name`, `interval`, `candles[]` (time, open, high, low, close), oldest first, only buckets with data

---

### Accounts (JWT Required)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/accounts/me` | Profile + balances |
| PUT | `/accounts/alias` | Set display alias |
| GET | `/accounts/transactions` | Transaction history |
| GET | `/accounts/summary` | Portfolio summary with margin breakdown |

**`GET /accounts/me`**  
Response: `UserInfo`

**`PUT /accounts/alias?alias=<name>`**  
Response: `UserInfo` (updated)

**`GET /accounts/transactions?limit=50`**  
Response: `TransactionHistoryResponse` — `wallet_address`, `transactions[]` (id, wallet_address, tx_type, amount, tx_hash, timestamp, related_position_id)

**`GET /accounts/summary`**  
Response: `PortfolioSummaryResponse`:
- `total_balance` = free_margin + wallet_balance + used_margin
- `free_margin` = free (unlocked) collateral inside the `CollateralVault` (after resting-order locks). This is the only balance the matching engine counts as order margin.
- `vault_free` = explicit alias of `free_margin` (vault-only, tradeable)
- `wallet_balance` = test-USDC held in the user's own wallet (e.g. an undeposited faucet claim). Visible in the UI, but not tradeable until the user calls `approve` + `vault.deposit`.
- `used_margin` = margin locked by open positions + margin reserved for resting orders
- `unrealized_pnl` = sum of unrealized PnL across open positions
- `realized_pnl` = from transaction history (not yet fully implemented)
- **SL/TP orders carry no separate margin reservation**

---

### Faucet (JWT Required)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/faucet/claim` | Claim test USDC (smart account address required) |

---

### WebSocket (Backend API, Port 8000)

| Endpoint | Subscribe Message | Server Pushes |
|----------|-------------------|---------------|
| `ws://localhost:8000/ws/price/{basket_name}` | `{"action":"subscribe","basket_name":"..."}` | `{"type":"price_update","basket_name":...,"index_price":...,"scaled_price":...,"computed_at":...,"constituent_count":...}` |
| `ws://localhost:8000/ws/orderbook/{basket_name}` | `{"action":"subscribe","basket_name":"..."}` | Depth snapshot (same as REST book endpoint) after every order |

Ping/pong: `{"action":"ping"}` → `{"type":"pong"}`

---

## Matching Engine (Port 8001)

### Orders (JWT Required)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/orders` | Safety-paused while legacy settlement is in use: 503 `legacy_settlement_disabled`; intended types: limit, market, stop, stop_loss, take_profit |
| GET | `/orders` | List orders (with status filter, pagination) |
| GET | `/orders/{order_id}` | Order status + fills |
| DELETE | `/orders/{order_id}` | Cancel resting order |

### Order Book (Public)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/baskets/{basket_name}/book` | Order book depth snapshot |

### Positions (JWT Required)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/positions` | List open positions for authenticated trader |

---

### Order Types & Required Fields

| Type | Description | Required Fields | Optional for SL/TP |
|------|-------------|-----------------|-------------------|
| `limit` | Price-time priority, GTC | `basket_name`, `side`, `size`, `leverage`, `price` | — |
| `market` | Fill-or-kill + slippage guard | `basket_name`, `side`, `size`, `leverage`, `max_slippage_bps` | — |
| `stop` | GTC, converts to market on trigger | `basket_name`, `side`, `size`, `leverage`, `trigger_price`, `max_slippage_bps` | — |
| `stop_loss` | Attached to position, OCO with TP, full close | `basket_name`, `position_id`, `trigger_price`, `max_slippage_bps` | `side`, `size`, `leverage`, `oco_group_id` |
| `take_profit` | Attached to position, OCO with SL, full close | `basket_name`, `position_id`, `trigger_price`, `max_slippage_bps` | `side`, `size`, `leverage`, `oco_group_id` |

**SL/TP field derivation:** If `side`, `size`, `leverage` omitted, server derives from position:
- `size` = position size
- `leverage` = position leverage  
- `side` = closing side (opposite of position side)

**SL/TP field validation:** If client provides `side`, `size`, `leverage`, they must exactly match derived values; mismatch → 422 `sl_tp_field_mismatch`.

**`position_id`** must belong to authenticated trader; otherwise 403. Non-existent or closed position → 422 `position_not_found`.

**`oco_group_id`**: Server assigns automatically when both SL and TP placed for same position. Accepts client-supplied ID if unique to that position.

---

### Order Placement: `POST /orders`

Request: `OrderRequest` (see fields above)  
Response (201): `OrderResponse` with `order_id`, `status`, `fills[]`, `failed_fills[]`, `margin_check`

**Margin pre-check** (all except SL/TP): validates basket tradeable, oracle fresh, leverage ≤ cap, free vault balance ≥ required margin (`oracle_price * size / leverage`).

**Rejection codes (422):** `oracle_price_stale`, `insufficient_margin`, `basket_not_tradeable`, `price_not_on_tick`, `size_below_min`, `leverage_out_of_range`, `leverage_above_cap`, `oracle_price_zero`, `unknown_basket`, `max_slippage_bps_required`, `trigger_price_required`, `position_id_required`, `price_required_for_limit_orders`, `sl_tp_field_mismatch`, `position_not_found`, `no_liquidity`, `insufficient_liquidity`, `fok_failed`, `self_trade`, `oracle_unreadable`, `leverage_cap_unreadable`, `invalid_slippage_bps`, `invalid_trigger_price`, `settlement_failed`, `oco_cancelled`.

**Settlement:** Fills confirmed only when `PositionManager.updatePosition` transaction mined (receipt status 1). On-chain entry price = oracle price at match time. Settlement failure → order `rejected`, fill `confirmed: false`.

---

### Order List: `GET /orders`

Query:
- `status` = `open` | `history` | `all` (default `open`)
  - `open` = `open`, `partially_filled`, plus resting untriggered stop/SL/TP
  - `history` = `filled`, `cancelled`, `rejected`, `triggered`
- `basket_name` (optional)
- `limit` (default 50, max 200)
- `cursor` (order_id for pagination, returns older orders)

Response: `OrderListResponse` — `orders[]` (OrderListItem), `cursor`, `has_more`  
OrderListItem: all OrderResponse fields + `updated_at`, `average_fill_price` (nullable)  
Sorted newest first.

---

### Order Status: `GET /orders/{order_id}`

Response: `OrderResponse`:
- `order_id`, `basket_name`, `trader`, `side`, `order_type`, `price`, `trigger_price`, `size`, `filled_size`, `remaining`, `leverage`, `status`, `rejection_reason`, `created_at`, `fills[]`, `failed_fills[]`, `margin_check`, `position_id`, `oco_group_id`, `average_fill_price`

**OrderStatus enum:** `open`, `partially_filled`, `filled`, `cancelled`, `rejected`, `triggered`

---

### Cancel Order: `DELETE /orders/{order_id}`

Response: `CancelResponse` — `order_id`, `status`, `message`  
Errors: 404 not found, 403 not your order, 409 cannot cancel (filled/rejected)

---

### Positions: `GET /positions`

Response: `PositionsResponse` — `positions[]` (PositionResponse):
- `position_id` (format: `wallet_basket`), `basket_name`, `side` (`long`/`short`), `size`, `leverage`, `entry_price`, `mark_price`, `margin_usdc`
- `liquidation_price` (nullable — requires maintenance margin param on-chain)
- `unrealized_pnl_abs`, `unrealized_pnl_pct`
- `stop_loss_price`, `take_profit_price` (from resting SL/TP orders)
- `stop_loss_order_id`, `take_profit_order_id`, `oco_group_id`
- `fee_paid` (nullable — not tracked)
- `opened_at` (nullable — not available on-chain)

**Mark price & PnL** use same oracle source as trigger logic.  
**Never invent numbers** — null returned when not derivable.

---

### Order Book: `GET /baskets/{basket_name}/book`

Response: `BookSnapshot`:
- `basket_name`, `bids[]` (price, size), `asks[]` (price, size), best_bid, best_ask, mid_price, spread, ts
- Levels aggregated (price, total size), best price first, limit orders only, GTC

---

## Changes from Previous Version

### Auth Unification (Workstream A)
- Matching engine now accepts **only** internal HS256 token (same as backend API)
- Removed Dynamic JWT verification from matching engine
- Shared `InternalJWTVerifier` in `shared/xleuth_shared/auth/internal_jwt.py`
- Machine-readable 401 codes: `token_missing`, `token_expired`, `token_invalid`
- CORS added to matching engine via `CORS_ALLOWED_ORIGINS` (default: `http://localhost:8080,http://localhost:3000`)

### SL/TP Request Schema (Workstream B)
- `side`, `size`, `leverage` now optional for `stop_loss`/`take_profit`
- Derived from position if omitted; validated if provided
- New rejection code: `sl_tp_field_mismatch`
- Typed response models: `OrderResponse`, `CancelResponse`, `BookSnapshot`, `OrderListResponse`, `PositionsResponse`, `PortfolioSummaryResponse`, `CandlesResponse`
- Enums: `OrderStatus`, `RejectionCode`

### Read Endpoints (Workstream C)
- `GET /orders` (matching engine) — paginated, filterable order list
- `GET /positions` (matching engine) — open positions from on-chain
- `GET /accounts/summary` (backend API) — portfolio margin breakdown
- `GET /baskets/{name}/candles` (backend API) — OHLC from TimescaleDB
- `GET /baskets` & `GET /baskets/{name}/price` — added `change_24h_abs`, `change_24h_pct` (nullable)

### OpenAPI
- All responses now have typed `response_model` for codegen
- Enums and rejection codes documented in schemas
