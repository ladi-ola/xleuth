# API Contract — Xleuth (for frontend handoff)

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

Wallet-native SIWE (Sign-In With Ethereum) → short-lived JWT. No passwords.

1. `GET /auth/nonce/{wallet_address}`
   Returns `{ nonce, wallet_address, message }` where `message` is the full
   SIWE message the wallet must sign.
2. Wallet signs `message` (EIP-191 personal_sign) → `POST /auth/login`
   Body: `{ wallet_address, signature, message, nonce }`.
   The backend verifies the signature against the nonce and the SIWE message,
   upserts the user, and returns:
   `{ access_token, token_type: "Bearer", expires_in_minutes }`.
3. Every authenticated endpoint takes the token as an `Authorization: Bearer
   <token>` header. The token's `sub` is the wallet address (lowercased);
   that wallet is the acting user everywhere (orders, account data).

Endpoints: `GET /auth/me` returns the current user's profile.

## 2. Backend API (port 8000)

### Baskets — public, no auth

| Endpoint | Description |
|---|---|
| `GET /baskets` | List all baskets with latest index price, lifecycle `status` (`active` / `upcoming` / `resolved`) and `is_tradeable`. |
| `GET /baskets/{name}/price` | Latest computed index price for one basket. `index_price` is the raw float (e.g. `0.1527`), `scaled_price` is the 0–100 index-point value used on-chain and in trading (e.g. `15.28`). |
| `GET /baskets/{name}/history` | Time series of computed prices (`[{ts, basket_name, index_price, scaled_price, constituent_count}]`), newest last. |
| `GET /baskets/{name}/constituents` | Constituent Polymarket markets that make up the basket: `{ condition_id, clob_token_id, event_id, question, end_date, price, volume, price_source, sub_markets, sub_market_count }` plus `markets_filtered_out` / `excluded_markets`. |

Basket names look like `TOP20-AUGUST` (year-less → current year) or
`TOP20-JANUARY-2027` (explicit year). A basket that has reached its target
month is `resolved` / `is_tradeable: false`.

### Accounts — JWT required

| Endpoint | Description |
|---|---|
| `GET /accounts/me` | Profile + balances: `{ wallet_address, alias, balance, realized_pnl, unrealized_pnl, created_at }`. |
| `PUT /accounts/alias?alias=<name>` | Set display alias (query param). |
| `GET /accounts/transactions?limit=50` | Transaction history: `{ id, wallet_address, tx_type, amount, tx_hash, timestamp, related_position_id }`. |

## 3. Matching engine (port 8001)

Trading lives here; auth is the same shared JWT (matching engine validates the
same secret, `sub` = wallet).

| Endpoint | Description |
|---|---|
| `POST /orders` | Place a limit order (JWT required). Body: `{ basket_name, side: "buy"\|"sell", price, size, leverage }`. |
| `GET /orders/{order_id}` | Order status + fills (JWT, owner only). |
| `DELETE /orders/{order_id}` | Cancel a resting order (JWT, owner only). |
| `GET /baskets/{name}/book` | Order book depth snapshot (public). |

### Order placement contract

- Price is in 0–100 index points, must be on `tick_size` (0.01); `size` must
  be ≥ `min_order_size` (10); leverage 1–`max_leverage`.
- Before accepting, the engine pre-checks against **live on-chain state**:
  basket tradeable, oracle price fresh, leverage cap, and free vault balance
  ≥ required margin (`price * size / leverage` USDC).
- Rejections return HTTP 422 with a machine-readable `detail`, e.g.:
  - `oracle_price_stale`
  - `insufficient_margin`
  - `basket_not_tradeable`
  - `price_not_on_tick`, `size_below_min`, `leverage_out_of_range`,
    `leverage_above_cap`, `oracle_price_zero`, `unknown_basket`
- Placement returns HTTP 201 with the order and its fills:
  ```json
  {
    "order_id": "…", "basket_name": "TOP20-AUGUST", "trader": "0x…",
    "side": "buy", "price": 30.0, "size": 20.0, "leverage": 5,
    "status": "filled", "filled_size": 20.0, "remaining": 0.0,
    "rejection_reason": null, "created_at": "…",
    "fills": [{
      "trade_id": "…", "basket_name": "TOP20-AUGUST",
      "price": 30.0, "size": 20.0,
      "taker_order_id": "…", "maker_order_id": "…",
      "taker_trader": "0x…", "maker_trader": "0x…",
      "taker_side": "sell", "maker_side": "buy",
      "notional": 600.0, "confirmed": true,
      "tx_hash": "0x…", "error": null, "ts": "…"
    }],
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

### Order book depth (`GET /baskets/{name}/book`)

```json
{
  "basket_name": "TOP20-AUGUST",
  "bids": [[30.0, 20.0], [29.5, 5.0]],
  "asks": [[31.0, 15.0]],
  "best_bid": 30.0, "best_ask": 31.0,
  "mid_price": 30.5, "spread": 1.0,
  "ts": "2026-08-08T…Z"
}
```
Levels are `[price, total_size]`, best price first, per-basket, price-time
priority matching, limit orders only, GTC.

## 4. WebSocket streams (backend API, port 8000)

| Endpoint | Message you send | What you get |
|---|---|---|
| `ws://localhost:8000/ws/price/{basket_name}` | `{"action":"ping"}` → `{"type":"pong"}`; `{"action":"subscribe","basket_name":"TOP20-AUGUST"}` → `{"type":"subscribed",...}` | Server pushes `{"type":"price_update","basket_name":…,"index_price":…,"scaled_price":…,"computed_at":…,"constituent_count":…}` every time a new index price is computed (Redis pub/sub `xleuth:basket:{name}:price`; DB-poll fallback every 5s if Redis is down). |
| `ws://localhost:8000/ws/orderbook/{basket_name}` | same ping/subscribe pattern | Server pushes the **depth snapshot** (same shape as the REST book endpoint) after every accepted/cancelled order (Redis `xleuth:basket:{name}:book`). |

Malformed client messages get `{"type":"error","message":"Invalid message
format"}`. Both streams auto-reconnect-friendly (send `ping` to check liveness).
