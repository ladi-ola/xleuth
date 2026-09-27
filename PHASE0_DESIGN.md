# Phase 0: Audit + Design Document

## 1. Current Resting Limit Order Flow (Template for New Order Types)

### 1.1 Schema
- **Location**: `matching-engine/src/xleuth_matching/api.py` → `OrderRequest` model
- **Fields**: `basket_name`, `side` (buy/sell), `price` (float, tick-aligned), `size` (float), `leverage` (int)
- **Shared schemas**: None currently — order schemas live in matching-engine only

### 1.2 Margin Reservation
- **File**: `matching-engine/src/xleuth_matching/margin_check.py` → `MarginCheck.validate()`
- **Logic**: `required_margin = (oracle_price * size) / leverage`
- **Check**: `free_balance(wallet) >= required_margin` (reads `CollateralVault.freeBalance` on-chain)
- **Timing**: At order placement only — margin is **not** locked on-chain until a fill occurs
- **On-chain locking**: Happens in `PositionManager.updatePosition` → `CollateralVault.lockMargin` during settlement

### 1.3 Signed-Authorization Capture/Storage
- **CURRENT BEHAVIOR (differs from Section 3 assumption)**:
  - The matching engine reads `TRADER{1,2,...}_PRIVATE_KEY` from environment at startup
  - At fill time, `Web3TxSubmitter.submit()` signs `PositionManager.updatePosition` with the trader's private key from env
  - **No trader signature is captured at placement time** — the backend holds the private keys and signs at match time
- **Section 3 Assumption**: "trader signs once at placement, the backend holds that signature, and relays it at trigger/match time"
- **VERDICT**: The assumption is **INCORRECT** for the current implementation. The backend holds private keys, not signatures.

### 1.4 Book Matching (`orderbook.py`)
- **Engine**: Wraps `order-matching` PyPI package (`MatchingEngine`)
- **Order type**: `Execution.LIMIT` only
- **Priority**: Price-time (best price first, FIFO within price level)
- **Self-trade guard**: Rejects orders that would cross same trader's resting order
- **Order lifecycle**: `OPEN` → `PARTIALLY_FILLED` → `FILLED` (or `CANCELLED` / `REJECTED`)
- **Fills**: Produced in `BasketOrderBook.place()` → `_apply_trade()` → `_settle_own_trades()`

### 1.5 Resolution-Time Cancellation
- **Current state**: **NOT IMPLEMENTED**
- `SettlementEngine.settleBasket()` calls `PositionManager.settleBasket()` which closes all positions
- No logic exists to cancel resting limit orders when a basket resolves
- Orders would remain in the book indefinitely after resolution

---

## 2. Settlement/Signature Mechanism — Confirmation & Correction

### Current Mechanism (Week 5 Implementation)
```python
# matching-engine/src/xleuth_matching/settlement.py
class Web3TxSubmitter(TxSubmitter):
    def submit(self, update: PositionUpdate) -> tuple[str, dict]:
        key = self._keys.get(update.wallet.lower())  # from TRADER_PRIVATE_KEY env vars
        account = Account.from_key(key)
        # ... build and sign transaction with account ...
```

### Section 3 Spec Assumption
> "Stop and SL/TP orders must relay through the exact same trader-signed-authorization mechanism settlement.py already uses for matched limit-order fills — the trader signs once at placement, the backend holds that signature, and relays it at trigger/match time with no trader present"

### **Critical Design Decision Required**
The current implementation uses **backend-held private keys** (env vars), not **trader-captured signatures**. Two paths forward:

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A: Keep backend keys** | Continue using TRADER_PRIVATE_KEY env vars for all order types | Simpler, matches current v1 implementation | Custodial; not "trader signs once" |
| **B: Implement EIP-712 signatures** | Trader signs typed data at placement; backend stores signature; submits via `PositionManager.updatePositionWithSig` (new contract method) | Non-custodial, matches spec | Requires contract changes (new `updatePositionWithSig`), more complex |

**RECOMMENDATION**: **Option A** for this MVP pass. The spec says "Confirm in Phase 0... If it works differently, STOP and report before implementing." — We are reporting: the current mechanism uses backend-held keys. Implementing Option B would require contract changes (new `updatePositionWithSig` method in PositionManager) which Section 3 says "expected: no" contract changes. We should proceed with Option A and document this deviation.

---

## 3. Auth: matching-engine vs backend-api JWT Relationship

### Current Flow
```
Frontend (Dynamic.xyz) → backend-api /auth/login (SIWE) → HS256 JWT (shared JWT_SECRET)
                                              ↓
                                    matching-engine validates same JWT with same secret
```

### Details
- **backend-api** (`backend-api/src/xleuth_api/auth/`):
  - `SIWEHandler`: Generates nonce, builds SIWE message, verifies `personal_sign`
  - `JWTHandler`: Issues HS256 JWT with `sub=wallet_address`, 60-min expiry
  - `/auth/nonce/{wallet}` → `/auth/login` → returns `access_token`

- **matching-engine** (`matching-engine/src/xleuth_matching/api.py`):
  - `get_wallet()` dependency: Decodes Bearer token with `engine.config.jwt_secret` (HS256)
  - Extracts `sub` as wallet address
  - **No delegation** — independent verification using same secret

### JWKS Replacement Impact
| Service | Current | After JWKS |
|---------|---------|------------|
| backend-api | SIWE → HS256 JWT | Dynamic JWKS → HS256 JWT (or pass-through Dynamic JWT) |
| matching-engine | HS256 verify (shared secret) | **Must change**: Verify against Dynamic JWKS (RS256/ES256) |

**Key Insight**: The matching-engine cannot continue using HS256 verification if backend-api stops issuing HS256 tokens. Both services must verify against Dynamic's JWKS endpoint.

---

## 4. Design Proposal: Stop Orders & SL/TP Orders

### 4.1 Schema Changes (`shared/xleuth_shared/schemas/orders.py` — NEW FILE)

```python
# shared/xleuth_shared/schemas/orders.py
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime

class OrderType(str, Enum):
    LIMIT = "limit"
    MARKET = "market"
    STOP = "stop"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"

class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"

class OrderStatus(str, Enum):
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    TRIGGERED = "triggered"  # For stop/stop-loss/take-profit

# Base order request (extends current OrderRequest)
class BaseOrderRequest(BaseModel):
    basket_name: str
    side: OrderSide
    size: float = Field(gt=0)
    leverage: int = Field(ge=1)
    order_type: OrderType = OrderType.LIMIT

# Limit order (existing)
class LimitOrderRequest(BaseOrderRequest):
    order_type: Literal[OrderType.LIMIT] = OrderType.LIMIT
    price: float = Field(gt=0)  # Required for limit

# Market order (FOK + slippage guard)
class MarketOrderRequest(BaseOrderRequest):
    order_type: Literal[OrderType.MARKET] = OrderType.MARKET
    max_slippage_bps: int = Field(ge=0, le=10000)  # Max slippage in basis points
    # No price field — fills at best available up to slippage guard

# Stop order (standalone, GTC, converts to market on trigger)
class StopOrderRequest(BaseOrderRequest):
    order_type: Literal[OrderType.STOP] = OrderType.STOP
    trigger_price: float = Field(gt=0)  # Mark/index price trigger
    max_slippage_bps: int = Field(ge=0, le=10000)

# Stop-Loss / Take-Profit (attached to position, OCO)
class SLTPOrderRequest(BaseOrderRequest):
    order_type: Literal[OrderType.STOP_LOSS, OrderType.TAKE_PROFIT]
    trigger_price: float = Field(gt=0)
    position_id: str  # Reference to open position
    max_slippage_bps: int = Field(ge=0, le=10000)
    # No size — always full position close
    # No leverage — uses position's leverage

# Unified response
class OrderResponse(BaseModel):
    order_id: str
    basket_name: str
    trader: str
    side: OrderSide
    order_type: OrderType
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    size: float
    filled_size: float
    remaining: float
    leverage: int
    status: OrderStatus
    rejection_reason: Optional[str] = None
    created_at: datetime
    fills: list = []
    # SL/TP specific
    position_id: Optional[str] = None
    oco_group_id: Optional[str] = None  # For OCO pairing
```

### 4.2 Margin Reservation

| Order Type | Margin Reservation Timing | Amount |
|------------|---------------------------|--------|
| Limit | At placement (pre-check only) | `(oracle_price * size) / leverage` |
| Market | At placement (pre-check only) | `(oracle_price * size) / leverage` |
| Stop | **At placement** (not deferred) | `(oracle_price * size) / leverage` |
| SL/TP | **At placement** (not deferred) | **None additional** — position already has margin locked |

**Rationale**: Section 3 explicitly states stop orders "reserves/locks margin against the trader's available collateral at the moment the order is placed — not deferred to trigger time" and "Margin accounting must never double-count: a position's SL/TP orders don't get a separate margin reservation on top of the position's own margin."

### 4.3 Trigger Evaluation Architecture

**DECISION**: Trigger evaluation lives in **matching-engine**, reading prices from the same source as margin checks (IndexOracleConsumer on-chain).

**Rationale**:
- Matching-engine already has `Web3ChainState.oracle_price()` reading from `IndexOracleConsumer`
- Oracle-service pushes prices to `IndexOracleConsumer` — matching-engine reads the same source
- Keeps trigger evaluation co-located with order book and settlement
- Avoids adding a new service or complex inter-service communication

**Implementation**:
- Background task in matching-engine (APScheduler) polls oracle prices per basket every N seconds (configurable, e.g., 5s)
- For each basket, evaluate resting stop/SL-TP orders against latest oracle price
- On trigger: convert to market order (FOK + slippage) and execute through existing settlement path

### 4.4 Trigger-to-Execution Flow

```
1. Background task reads oracle price for basket
2. For each resting STOP order:
   - BUY stop: trigger if oracle_price >= trigger_price
   - SELL stop: trigger if oracle_price <= trigger_price
3. On trigger:
   a. Mark order status = TRIGGERED
   b. Create internal MarketOrderRequest with:
      - Same basket, side, size, leverage
      - max_slippage_bps from stop order
   c. Execute through margin_check.validate() → book.place() → settlement
   d. If FOK fails (insufficient depth / slippage): order stays TRIGGERED? REJECTED? → **OPEN QUESTION**
4. For SL/TP:
   a. Same trigger logic (mark/index price)
   b. On trigger: execute as MARKET order to CLOSE position (size = position size, opposite side)
   c. OCO: Cancel sibling order immediately
```

### 4.5 OCO Enforcement (SL/TP)

- At placement: Accept SL and TP together (or separately) with same `position_id`
- Generate shared `oco_group_id` (UUID)
- Store mapping: `position_id` → `{stop_loss_order_id, take_profit_order_id}`
- On either trigger:
  1. Execute triggered order
  2. Cancel sibling via `BasketOrderBook.cancel(sibling_id)`
  3. Remove from OCO mapping

### 4.6 Position-Close Auto-Cancellation

- When a position closes (any means: manual, liquidation, settlement):
  - `PositionManager` emits `PositionClosed` event
  - Matching-engine must listen for this (or poll) and cancel any SL/TP orders for that `position_id`
  - **Implementation**: Add event listener in matching-engine for `PositionClosed` / `PositionSettled` / `PositionLiquidated` events

### 4.7 Basket Resolution Cancellation

- When `SettlementEngine.settleBasket()` succeeds:
  - All positions on basket are closed (emits `PositionClosed`)
  - Matching-engine cancels ALL resting orders (limit, stop, SL/TP) for that basket
  - **Implementation**: Listen for `BasketSettled` event from SettlementEngine

---

## 5. Design Proposal: JWKS Replacement (Dynamic.xyz)

### 5.1 Dynamic.xyz Configuration
- **Environment ID**: `938a93a5-ee1f-4da2-86cf-27326bd01885`
- **JWKS Endpoint**: `https://app.dynamic.xyz/api/v0/environments/{env_id}/jwks` (or similar)
- **Issuer**: `https://app.dynamic.xyz/environments/{env_id}`
- **Algorithm**: RS256 (Dynamic uses RSA keys)

### 5.2 Backend-API Changes (`backend-api/src/xleuth_api/auth/`)

**Files to REMOVE**:
- `siwe.py` — SIWE nonce generation, message building, signature verification
- `jwt.py` — HS256 token issuance/verification

**Files to ADD**:
- `dynamic_jwt.py` — JWKS client + JWT verification against Dynamic's keys

**New Flow**:
```
Frontend (Dynamic SDK) → gets Dynamic JWT → sends to backend-api
backend-api /auth/verify → verifies JWT against Dynamic JWKS → issues internal HS256 JWT (optional) OR passes Dynamic JWT through
```

**Decision**: Backend-api should **verify Dynamic JWT and issue its own HS256 JWT** for internal use (matching-engine compatibility during transition). Long-term, matching-engine also verifies Dynamic JWKS directly.

**Implementation** (`dynamic_jwt.py`):
```python
class DynamicJWTHandler:
    def __init__(self, environment_id: str, cache_ttl: int = 3600):
        self.jwks_url = f"https://app.dynamic.xyz/api/v0/environments/{environment_id}/jwks"
        self.issuer = f"https://app.dynamic.xyz/environments/{environment_id}"
        self._jwks_cache = None
        self._cache_expiry = 0
        self.cache_ttl = cache_ttl

    async def get_jwks(self) -> dict:
        # Cache JWKS with TTL
        ...

    async def verify_token(self, token: str) -> str | None:
        # 1. Get unverified header to find kid
        # 2. Fetch JWKS, find matching key
        # 3. Verify signature, exp, iss, aud
        # 4. Extract wallet from 'wallet_address' or 'sub' claim (Dynamic-specific)
        # 5. Return wallet address (lowercased)
        ...
```

**Endpoint Changes**:
- `GET /auth/nonce/{wallet}` → **REMOVE**
- `POST /auth/login` → **REPLACE** with `POST /auth/verify` accepting `{ token: string }` (Dynamic JWT)
- `GET /auth/me` → unchanged (uses verified wallet)

### 5.3 Matching-Engine Changes (`matching-engine/src/xleuth_matching/api.py`)

**Current**: `get_wallet()` uses `pyjwt.decode(token, jwt_secret, algorithms=["HS256"])`

**New**: Replace with Dynamic JWKS verification (same logic as backend-api's `DynamicJWTHandler`)

**Shared Code**: Create `shared/xleuth_shared/auth/dynamic_jwt.py` — both services import

### 5.4 JWT-to-Account Mapping

- Dynamic JWT contains wallet address in `wallet_address` claim (or `sub`)
- backend-api's `Database.upsert_user(wallet_address)` already keys by wallet
- **No schema change needed** — existing `users` table uses `wallet_address` as PK
- Matching-engine doesn't need DB — just extracts wallet from verified JWT

### 5.5 Files Summary

| Service | Remove | Add | Modify |
|---------|--------|-----|--------|
| backend-api | `siwe.py`, `jwt.py` | `dynamic_jwt.py` | `auth.py` routes, `main.py` deps, `dependencies.py` |
| matching-engine | — | — | `api.py` `get_wallet()`, `config.py` (remove jwt_secret?) |
| shared | — | `auth/dynamic_jwt.py` | — |

---

## 6. Contract Changes Assessment

### Current Contracts
| Contract | Purpose | Relevant to New Order Types? |
|----------|---------|------------------------------|
| `PositionManager` | Open/increase/flatten/close positions, margin locking | **No** — `updatePosition` handles all position deltas |
| `CollateralVault` | Custody, free/locked balance | **No** |
| `IndexOracleConsumer` | Price feed for mark/index price | **No** — stop/SL-TP triggers read same oracle |
| `SettlementEngine` | Basket expiry settlement | **No** — but emits events matching-engine must listen to |

### Conclusion
**No contract changes required** for market, stop, or SL/TP orders. All execute via existing `PositionManager.updatePosition` path.

**Caveat**: If we implement Option B (EIP-712 signatures), `PositionManager` would need `updatePositionWithSig`. But we're proceeding with Option A (backend keys).

---

## 7. Open Questions & Edge Cases (Section 3 Gaps)

### 7.1 Stop Order Trigger Failure Handling
**Scenario**: Stop triggers → converts to market order → FOK fails (insufficient depth / slippage exceeded)
- **Section 3 silent**: Does the stop order:
  - (a) Stay triggered and retry on next price tick?
  - (b) Convert to REJECTED and cancel?
  - (c) Remain as resting stop order (re-arm)?
- **Need decision** before Phase 3 implementation

### 7.2 Simultaneous SL + TP Trigger
**Scenario**: In a single price tick, both SL and TP trigger prices are crossed
- **Section 3**: "One-cancels-other: when either fills, cancel the sibling automatically"
- **Gap**: Which executes first? Both eligible simultaneously.
- **Proposal**: Process in price-order (TP before SL for longs, SL before TP for shorts) — but need explicit sign-off

### 7.3 Partial Fills + SL/TP
**Section 3**: "Full close only — no partial-size SL/TP"
- **But**: What if position is partially closed manually, then SL/TP triggers?
- **Current**: SL/TP size = position size at trigger time (full remaining)
- **Need confirmation**: Is this correct?

### 7.4 Stop Order Margin on Trigger
**Section 3**: "Reserves/locks margin at placement"
- **Current limit orders**: Margin pre-checked at placement, locked on-chain at fill
- **Stop orders**: Same — margin checked at placement, locked at trigger+fill
- **Gap**: What if margin becomes insufficient between placement and trigger (e.g., other positions opened)?
- **Proposal**: Re-validate margin at trigger time before executing market order. If fails → reject stop order.

### 7.5 Trigger Price Source
**Section 3**: "Trigger is the mark/index price, not last-traded price"
- **Current**: Oracle reads from `IndexOracleConsumer` (on-chain)
- **Matching-engine margin check**: Uses `Web3ChainState.oracle_price()` → same source
- **Confirmed**: Use on-chain `IndexOracleConsumer.latestPrice()` for triggers

### 7.6 Order ID Format for New Types
- Current: `uuid.uuid4().hex` (32-char hex)
- **Proposal**: Keep same format; `order_type` field distinguishes

### 7.7 WebSocket Events for New Order Types
- Current: Book updates on order placement/cancel
- **New events needed**: Stop triggered, SL/TP triggered, OCO cancellation
- **Channel**: Reuse `xleuth:basket:{name}:book` or new `xleuth:engine:events`?

### 7.8 Dynamic JWT Claims Mapping
- Need to confirm Dynamic's JWT claim structure for wallet address
- Common claims: `wallet_address`, `sub`, `address`
- **Need to verify** against Dynamic docs or test token

---

## 8. Phase 0 Sign-Off Request

Please confirm:

1. **Signature Mechanism**: Proceed with Option A (backend-held private keys) for all order types, deviating from "trader signs once" spec assumption?
2. **Stop Order Trigger Failure**: Behavior (a) retry, (b) reject, or (c) re-arm?
3. **Simultaneous SL+TP**: Process TP first for longs, SL first for shorts?
4. **Margin Re-validation at Trigger**: Re-check margin at stop/SL-TP trigger time?
5. **Dynamic JWT Claim**: Which claim holds wallet address? (Will test with Dynamic env ID)
6. **Contract Changes**: Confirmed no changes needed?

Once signed off, I'll proceed to **Phase 1: Auth Replacement**.