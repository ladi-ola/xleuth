# Xleuth Deployment Status — What's Live, Simulated, and Descoped

Last verified: 2026-08-08 (Week 6). Everything below runs on **Polygon Amoy
testnet (chain id 80002)** with test tokens — there is no mainnet
deployment and no real-money risk anywhere in this system today.

## What is LIVE (working end-to-end, verified this week)

- **Full pipeline proven on real data and real testnet:** live Polymarket
  prices → data-ingestion computes basket VWAP → oracle-service signs and
  pushes it on-chain → orders match in the matching engine → positions open
  on-chain → owner registers expiry → signed settle message relayed →
  SettlementEngine pays out. The Week-6 E2E test ran this with real tx
  hashes on three baskets (TOP20-JANUARY-2027, TOP20-FEBRUARY-2027,
  TOP20-OCTOBER/NOVEMBER) and passed.
- **Contracts on Amoy:**
  - CollateralVault `0x6dbeEb6a5bE0cD63159b1dBD5525dE125A1CECef`
  - PositionManager `0x65e2687284c64576d2B7Cd55393163Fb9f6871ef`
  - IndexOracleConsumer `0xd394B8A5dace5EB22933A2a0DCE1C82c1Eb70cd2`
  - SettlementEngine `0x68aa3697b1783cb671c575D01C5622c2FA8570e8`
  - MockUSDC `0xc8783E02f3EE944BdE2990DbcDFefbe8adc3e86D`
- **Services** (docker compose, all green):
  - `data-ingestion` — pulls Polymarket markets/ticks/volume, builds the
    monthly index, persists to TimescaleDB/Postgres, publishes price updates
    to Redis. Polls every 30s.
  - `backend-api` — REST + WebSocket on :8000 (baskets, auth, accounts,
    price/book streams).
  - `oracle-service` — every 15s reads the latest index from the DB, signs
    an EIP-712 price update and pushes it to IndexOracleConsumer on Amoy
    (live baskets TOP20-AUGUST, TOP20-SEPTEMBER currently).
  - `matching-engine` — limit-order matching + on-chain settlement on :8001.
  - `postgres` (TimescaleDB) + `redis`.
- **Live demo state on-chain today:** two open demo positions on
  TOP20-AUGUST (one long, one short, size 140 each, entry 24, margin 692
  USDC each) — tradeable and liquidatable while the oracle keeps the price
  fresh.
- **Baskets auto-rotate monthly:** `ACTIVE_BASKETS=TOP20-{MONTH}` expands to
  the current and next month; resolved baskets become read-only history.
- **Documentation:** OpenAPI specs + plain-English API contract
  (`docs/api-contract.md`), security self-review (`docs/security-review.md`).

## What is SIMULATED / TESTNET-ONLY

| Piece | Reality | Risk |
|---|---|---|
| Collateral | MockUSDC with an open faucet `mint()` — any user can mint test USDC | testnet only |
| Chain | Polygon Amoy public RPC (`publicnode.com`), chain 80002 | public testnet |
| Oracle signer | Single EOA (oracle-service key) signs all price updates | centralized (by design) |
| Settlement signer | Single EOA signs realized settle values | centralized (by design) |
| Market data | Real Polymarket API (Gamma for markets, CLOB for live ticks, data-api for live volume) — this part is real | API terms/rate limits |
| Realized settlement value | Off-chain service computes the basket's index; the E2E uses the fresh index price as the realized value pre-expiry (displaced by a small delta so one side wins) | honest pre-expiry proxy, not real market resolution |
| Order execution price | Entry price on-chain = oracle index price at match time; the fill/limit price is used for matching only | documented v1 design |

## What is EXPLICITLY DESCOPED (v1 / pre-audit)

- **Mainnet** — testnet only, no plans until a full external audit.
- **Decentralized oracle** — single authorized signer; rotation exists, no
  network of signers, no data-aggregation/fault-tolerance scheme.
- **Binary (binary-OUT) overlay** — the current product is cash-settled index
  futures on 0–100 index points; per-market binary resolution is not modeled.
- **Market orders / stops / IOC** — limit orders only, GTC, per-basket
  price-time priority.
- **Tiered/multi-level liquidation** — single maintenance-margin ratio with a
  permissionless liquidator + fee.
- **Trading fees** — no fee model in v1 (fees would be applied at the engine
  layer in a later milestone).
- **Insurance fund / socialized-loss pool** — a wiped side loses its margin
  (floored at zero); the residual shortfall is absorbed by the platform, and
  there is no dedicated insurance pool yet.
- **Formal security audit / fuzzing / invariant tests** — internal review
  only so far; see `docs/security-review.md` for the honest "not covered"
  list (no third-party audit, no Slither/Echidna, no MEV analysis, no
  gas-DoS mitigation for settlement at scale, no multisig/timelock on owner
  keys, no circuit breakers).
- **Frontend** — no UI ships yet; the API contract + OpenAPI specs are the
  handoff artifacts for the frontend build.

## How to run it

```bash
# each service dir ships a .env.example listing the keys it expects
# (backend-api/, data-ingestion/, oracle-service/, matching-engine/, contracts/);
# docker compose reads the root .env for all services.
cp backend-api/.env.example .env   # then fill in keys/addresses
docker compose up -d --build
# services: :8000 (API/WS), :8001 (matching)
# full end-to-end live test (real data -> Amoy settlement):
make test-e2e   # set E2E_BASKET_NAME to a fresh upcoming month after each run
```
