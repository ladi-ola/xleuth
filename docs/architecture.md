# Xleuth — V1 MVP Master Plan
**Scope:** Full-scope build, 6-week timeline, solo founder + agentic coder, 6–8 dev hours/day
**Goal:** A working testnet MVP suitable for early adopters and pre-seed fundraising

---

## 0. Locked Product Decisions (do not re-derive these — they are settled)

- **Universe:** Non-sport Polymarket markets only. Grouped by resolution window (weekly/monthly/quarterly/yearly).
- **Naming:** `TOP{N}-{MONTH}` (e.g. `TOP50-JULY`), unrelated-basket style (not thematic) for v1.
- **Index price:** Volume-weighted average price (VWAP) across filtered constituent markets. Multi-outcome markets (e.g. "What price will BTC hit in July?") are first VWAP'd internally across their own sub-outcomes to produce one price, then that single price enters the basket VWAP.
- **Liquidity filter:** Applied before any computation — illiquid markets are excluded entirely, not down-weighted.
- **Derivative type:** A **linear, cash-settled, dated index future** — NOT a perpetual. Each basket (e.g. `TOP50-JULY`) has an explicit expiry tied to when its constituent markets resolve. No funding-rate engine. At expiry, the contract settles to the **realized volume-weighted YES fraction** of the basket (0–1, or scaled 0–100), per your Q5 mechanics doc.
- **Execution model:** Off-chain order matching (price-time priority), on-chain settlement/custody. This is the Polymarket-style hybrid, not a fully on-chain CLOB and not a vAMM/pool.
- **Oracle:** Your backend computes the live index price and pushes signed updates on-chain at a fixed interval, using a single controlled key for MVP. Constituent-market resolution truth comes from Polymarket/UMA — that's an input to your computation, not a separate oracle system.
- **Network:** Polygon Amoy testnet only for this MVP. Mainnet is explicitly post-funding.
- **Collateral:** Test-USDC on Amoy.
- **Contracts:** Purpose-built minimal contracts, not a fork of an existing perp protocol — scoped tight enough to audit before mainnet.
- **Binary overlay ("will index settle > X"):** Explicitly out of scope for this 6 weeks. Data model must not block adding it later.
- **Team:** Solo + agentic coder for this phase; auditor/engineer hire happens post-raise.
- **Frontend:** You own design and the React implementation (via your own AI tooling). This plan covers everything the frontend consumes — it does not build the frontend itself, but Week 6 produces the API contract/handoff doc you need to wire it up.
- **No Syn reuse.** Fresh repo, no dependency on the Syn codebase.

---

## 1. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Backend language | Python 3.12 | Your stated preference; strong web3 tooling (`web3.py`) |
| API framework | FastAPI | Native async, WebSocket support, auto OpenAPI docs your frontend AI tool can consume directly |
| Database | PostgreSQL + TimescaleDB extension | Relational for users/positions/orders; Timescale hypertables are purpose-built for the index/market price time series you're storing |
| Cache / pub-sub | Redis | Live price broadcast to WebSocket clients, order book in-memory state, job locking |
| Background jobs | APScheduler (in-process) for v1 | Simpler ops than Celery for a solo team; periodic VWAP computation + oracle push jobs don't need a distributed queue yet |
| Matching engine base | `order-matching` (PyPI) or `dyn4mik3/OrderBook` (GitHub) | Real, existing price-time-priority Python matching engines — extend rather than write from zero |
| Smart contracts | Solidity + Foundry | Foundry's fast local testing (fuzzing, gas snapshots) matters more than Hardhat's tooling for a solo dev on a deadline |
| Contract libraries | OpenZeppelin (access control, reentrancy guards, SafeERC20) | Battle-tested primitives — do not hand-roll these |
| Chain interaction | `web3.py` (backend), Foundry scripts (deploy) | |
| Wallet auth | EIP-712 typed-data signing (Sign-In-With-Ethereum pattern) | No custody of private keys server-side; matches how Polymarket itself authenticates |
| Containerization | Docker Compose (Postgres, Redis, backend, oracle service, matching engine as separate services) | Keeps modules independently deployable later |

All thresholds, API keys, RPC URLs, contract addresses, oracle intervals, liquidity cutoffs, margin/leverage parameters, and fee rates live in `.env` — nothing described below should ever be hardcoded.

