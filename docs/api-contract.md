# API Contract — Xleuth (for frontend handoff)

> **2026-11-06 staged implementation:** New DB-backed baskets select within
> their explicit `[window_start, expiry_at)` resolution window, including the
> year. A midnight first-of-month exclusive expiry labels the preceding month.
> Live volume now comes from Polymarket Data API **v2 cumulative taker shares**;
> unavailable volume is not replaced with Gamma volume. Scaled price output
> supports 3 decimals. See [V2 execution status](relayed-execution-v2.md).
> The new signed-execution components are **not yet wired into `POST /orders`**;
> the legacy settlement/portfolio limitations in the security review remain.

Machine-readable specs are generated from the running FastAPI apps and
committed here:

- **Backend API** (baskets, auth, accounts, WebSocket): `docs/openapi/xleuth-api.json`
- **Matching Engine** (orders, order book): `docs/openapi/xleuth-matching.json`

Re-generate any time the services change:

```bash
# backend api
PYTHONPATH=backend-api/src:shared .venv/bin/python -c "
from dotenv import load_dotenv; load_dotenv()
from xleuth_api.main import create_app
import json; json.dump(create_app().openapi(), open('docs/openapi/xleuth-api.json','w'), indent=2)"
# matching engine
PYTHONPATH=matching-engine/src:shared .venv/bin/python -c "
from dotenv import load_dotenv; load_dotenv()
from xleuth_matching.api import create_app
from xleuth_matching.config import MatchingConfig
import json; json.dump(create_app(MatchingConfig.load()).openapi(), open('docs/openapi/xleuth-matching.json','w'), indent=2)"
```

Base URLs (local/dev): backend `http://localhost:8000`, matching
`http://localhost:8001`. Production contract addresses and chain: see
`deployment-status.md` (everything currently runs on Polygon Amoy testnet,
chain id 80002).

---

## 1. Auth flow (backend API)

Dynamic.xyz JWT verification → internal HS256 JWT. No passwords, no SIWE.

1. Frontend authenticates user via Dynamic.xyz SDK → receives Dynamic JWT
2. `POST /auth/verify` with Dynamic JWT
   Body: `{ "token": "<dynamic_jwt>" }`
   Backend verifies against Dynamic's JWKS (`https://app.dynamicauth.com/api/v0/sdk/{env_id}/.well-known/jwks`),
   upserts the user, and returns an internal HS256 JWT:
   `{ access_token, token_type: "Bearer", expires_in_minutes }`.
3. Every authenticated endpoint takes the **internal** token as an `Authorization: Bearer
   <token>` header. The token's `sub` is the wallet address (lowercased);
   that wallet is the acting user everywhere (orders, account data).

Endpoints: `GET /auth/me` returns the current user's profile.

**Note**: The old SIWE flow (`GET /auth/nonce/{wallet}`, `POST /auth/login`) has been removed.

---

## 2. Backend API (port 8000)

### Baskets — public, no auth

| Endpoint | Description |
|---|---|
| `GET /baskets` | List all baskets from the DB registry with latest index price, `slug`, `expiry_at`, `onchain_index_id`, registry `status` (`draft` / `registering` / `active` / `closed` / `settled` / `registration_failed`, surfaced as `active` / upcoming-like / `closed` / `settled` / `resolved`) and `is_tradeable`. |
| `GET /baskets/{name}/price` | Latest computed index price for one basket. `index_price` is the raw float (e.g. `0.1527`), `scaled_price` is the 0–100 index-point value used on-chain and in trading (e.g. `15.28`). |
| `GET /baskets/{name}/history` | Time series of computed prices (`[{ts, basket_name, index_price, scaled_price, constituent_count}]`), newest last. |
| `GET /baskets/{name}/constituents` | Constituent Polymarket markets that make up the basket: `{ condition_id, clob_token_id, event_id, question, end_date, price, volume, price_source, sub_markets, sub_market_count }` plus `markets_filtered_out` / `excluded_markets`. |

Basket names look like `TOP20-OCTOBER` (generated display labels
`{THEME}{COUNT}-{EXPIRY}`; the immutable key is a year-qualified slug such as
`top20-2026-10`). Names are never parsed — theme/count/expiry come from DB
columns. Only `active`, unexpired baskets with an `onchain_index_id` are
tradeable; `GET /baskets` also returns `slug`, `expiry_at` and
`onchain_index_id` per basket.

### Accounts — JWT required

| Endpoint | Description |
|---|---|
| `GET /accounts/me` | Profile + balances: `{ wallet_address, alias, balance, realized_pnl, unrealized_pnl, created_at }`. |
| `PUT /accounts/alias?alias=<name>` | Set display alias (query param). |
| `GET /accounts/transactions?limit=50` | Transaction history: `{ id, wallet_address, tx_type, amount, tx_hash, timestamp, related_position_id }`. |

---

## 3. Matching engine (port 8001)

Trading lives here; auth uses Dynamic JWT verification (same env ID as backend).

| Endpoint | Description |
|---|---|
| `POST /orders` | Place a limit, market, stop, stop-loss, or take-profit order (JWT required). |
| `GET /orders/{order_id}` | Order status + fills (JWT, owner only). |
| `DELETE /orders/{order_id}` | Cancel a resting order (JWT, owner only). |
| `GET /baskets/{name}/book` | Order book depth snapshot (public). |

### Order Types

| Type | Description | Required Fields |
|---|---|---|
| `limit` | Price-time priority, rests in book GTC | `price`, `size`, `leverage` |
| `market` | Fill-or-kill with slippage guard | `size`, `leverage`, `max_slippage_bps` |
| `stop` | Standalone GTC, converts to market on trigger | `trigger_price`, `size`, `leverage`, `max_slippage_bps` |
| `stop_loss` | Attached to position, OCO with TP, full close | `position_id`, `trigger_price`, `max_slippage_bps` |
| `take_profit` | Attached to position, OCO with SL, full close | `position_id`, `trigger_price`, `max_slippage_bps` |

### Common Order Fields

- `basket_name`: string (e.g., `TOP20-SEPTEMBER`)
- `side`: `"buy"` | `"sell"`
- `size`: float (> 0; `price * size` must be ≥ `min_order_size` = 10 USDC)
- `leverage`: int (1–`max_leverage` = 5)
- `order_type`: `"limit"` | `"market"` | `"stop"` | `"stop_loss"` | `"take_profit"` (default: `"limit"`)
- `price`: float (> 0, on tick 0.01) — **required for limit only**
- `max_slippage_bps`: int (0–10000) — **required for market, stop, stop_loss, take_profit**
- `trigger_price`: float (> 0) — **required for stop, stop_loss, take_profit**
- `position_id`: string — **required for stop_loss, take_profit**
- `oco_group_id`: string (optional) — links stop_loss + take_profit for OCO

### Order Placement Contract

- Price is in 0–100 index points, must be on `tick_size` (0.01); the order
  notional `price * size` must be ≥ `min_order_size` (10 USDC); leverage
  1–`max_leverage`.
- `Idempotency-Key` header (optional): replaying a key within 24h returns the
  original order instead of placing a duplicate (same wallet). The UI sends
  one key per trade dialog.
- Rate limits: `POST /orders` 120/min/IP (429 + `Retry-After`); bodies over
  1MB are rejected (413). Auth/faucet endpoints: 30/10 per min/IP.
- Before accepting, the engine pre-checks against **live on-chain state**:
  basket tradeable, oracle price fresh, leverage cap, and free vault balance
  ≥ required margin (`oracle_price * size / leverage` USDC).
- Rejections return HTTP 422 with a machine-readable `detail`, e.g.:
  - `oracle_price_stale`
  - `insufficient_margin`
  - `basket_not_tradeable`
  - `price_not_on_tick`, `size_below_min`, `leverage_out_of_range`,
    `leverage_above_cap`, `oracle_price_zero`, `unknown_basket`
  - `max_slippage_bps required`, `trigger_price required`, `position_id required`
  - `price required for limit orders`
- **Margin**: Uses on-chain oracle price (not order price). For stop/SL-TP orders,
  margin is reserved at placement (stop) or no additional margin (SL-TP, position
  already has margin).
- Placement returns HTTP 201 with the order and its fills:
  ```json
  {
    "order_id": "…", "basket_name": "TOP20-SEPTEMBER", "trader": "0x…",
    "side": "buy", "order_type": "market", "price": 30.0, "size": 20.0, "leverage": 5,
    "trigger_price": 55.0, "position_id": "pos-1", "oco_group_id": "oco-1",
    "status": "filled", "filled_size": 20.0, "remaining": 0.0,
    "rejection_reason": null, "created_at": "…",
    "fills": [{
      "trade_id": "…", "basket_name": "TOP20-SEPTEMBER",
      "price": 30.0, "size": 20.0,
      "taker_order_id": "…", "maker_order_id": "…",
      "taker_trader": "0x…", "maker_trader": "0x…",
      "taker_side": "sell", "maker_side": "buy",
      "notional": 600.0, "confirmed": true,
      "tx_hash": "0x…", "error": null, "ts": "…"
    }],
    "failed_fills": [],
    "margin_check": { "ok": true, "reason": null, "details": {"oracle_price": 24, "required_usdc": 96.0} }
  }
  ```
- `confirmed: true` means the position change was **mined on-chain** (receipt
  status 1) — a fill is never confirmed without its PositionManager
  `updatePosition` transaction. Entry price on-chain is the **oracle price** at
  match time (fill price is execution/matching-only in v1).
- If on-chain settlement fails, the order is marked `rejected` with
  `rejection_reason: "settlement failed: …"` and the fill has `confirmed:
  false` + `error`.

### Order Behavior by Type

**Limit** (existing): Price-time priority, rests in book GTC, can be partially filled.

**Market**: Fill-or-kill with slippage guard. Walks the book (best price first)
until full size filled or rejected. Rejected if insufficient liquidity within
`max_slippage_bps` (BUY: `best_ask * (1 + bps/10000)`, SELL: `best_bid * (1 - bps/10000)`).
Self-trade guard applies.

**Stop**: GTC, rests off-book. Triggers when mark/index price crosses
`trigger_price` (BUY stop: price ≥ trigger, SELL stop: price ≤ trigger).
Converts to market order (same FOK + slippage semantics). Margin reserved at
placement. Evaluated every 5s (configurable) against `IndexOracleConsumer` price.

**Stop-Loss / Take-Profit**: Attached to a `position_id`, full-close only.
OCO (one-cancels-other): same `oco_group_id` links SL and TP.
- Long position: SL sell triggers at price ≤ trigger, TP sell triggers at price ≥ trigger
- Short position: SL buy triggers at price ≥ trigger, TP buy triggers at price ≤ trigger
No additional margin (position already has margin locked). Evaluated same as stop orders.
On trigger: converts to market order, executes FOK, cancels sibling via OCO.

### Order book depth (`GET /baskets/{name}/book`)

```json
{
  "basket_name": "TOP20-SEPTEMBER",
  "bids": [[30.0, 20.0], [29.5, 5.0]],
  "asks": [[31.0, 15.0]],
  "best_bid": 30.0, "best_ask": 31.0,
  "mid_price": 30.5, "spread": 1.0,
  "ts": "2026-08-08T…Z"
}
```
Levels are `[price, total_size]`, best price first, per-basket, price-time
priority matching, limit orders only, GTC.

---

## 4. WebSocket streams (backend API, port 8000)

| Endpoint | Message you send | What you get |
|---|---|---|
| `ws://localhost:8000/ws/price/{basket_name}` | `{"action":"ping"}` → `{"type":"pong"}`; `{"action":"subscribe","basket_name":"TOP20-SEPTEMBER"}` → `{"type":"subscribed",...}` | Server pushes `{"type":"price_update","basket_name":…,"index_price":…,"scaled_price":…,"computed_at":…,"constituent_count":…}` every time a new index price is computed (Redis pub/sub `xleuth:basket:{name}:price`; DB-poll fallback every 5s if Redis is down). |
| `ws://localhost:8000/ws/orderbook/{basket_name}` | same ping/subscribe pattern | Server pushes the **depth snapshot** (same shape as the REST book endpoint) after every accepted/cancelled order (Redis `xleuth:basket:{name}:book`). |

Malformed client messages get `{"type":"error","message":"Invalid message
format"}`. Both streams auto-reconnect-friendly (send `ping` to check liveness).
