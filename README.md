# Xleuth — Leveraged prediction-market index baskets (Polygon Amoy testnet)

> Testnet only (test USDC, no real funds). See `PLAN.md`, `ADMIN_BASKET_GUIDE.md`,
> `TECHNICAL_DOCUMENTATION.md`, and `docs/deployment-status.md`.

## 1. What this is

React SPA + FastAPI `backend-api` (`:8000`) + `matching-engine` (`:8001`) +
`oracle-service` + `data-ingestion` + Postgres/Timescale + Redis + Foundry contracts.
Baskets are data in the `baskets` DB table — created only via `admin-cli/` (`make basket-*`).
Auth is Dynamic.xyz JWT → internal HS256 JWT (no SIWE).

## 2. Quick start

```bash
docker compose up -d        # postgres + redis + 4 python services
make run-api                # backend-api :8000 (local, no docker)
make run-matching           # matching-engine :8001
make run-ingestion          # Polymarket poller
make test-all               # all python suites
cd contracts && forge test --gas-report
```

## 3. Repository Structure

```
xleuth/
├── .env                                 # root env consumed by docker-compose (see per-service .env.example)
├── .gitignore
├── .gitmodules                          # contracts/lib submodules (forge-std, openzeppelin-contracts)
├── README.md
├── PLAN.md                              # Task 1 trading QA / Task 2 landing and waitlist
├── ADMIN_BASKET_GUIDE.md                # admin-only basket CLI guide (git-ignored upstream)
├── TECHNICAL_DOCUMENTATION.md           # full technical reference (generated 2026-10-12)
├── docker-compose.yml                   # postgres + redis + data-ingestion/backend-api/oracle/matching-engine
├── Makefile                            # test/run/basket-*/deploy-* targets
│
├── docs/
│   ├── architecture.md                 # module boundaries, data flow diagram
│   ├── api-contract.md                 # plain-English API/WS contract for frontend handoff
│   ├── API_SURFACE.md                  # endpoint surface summary
│   ├── analytics.md                    # cookieless analytics event spec
│   ├── basket-runbook.md               # make basket-* procedures + rollover
│   ├── deployment-status.md            # what's live vs. simulated vs. explicitly descoped
│   ├── deployment-https.md             # HTTPS/HSTS/CSP runbook
│   ├── programmatic-seo.md             # basket-page SEO policy
│   ├── privacy-policy.md               # source for /privacy
│   ├── terms.md                        # source for /terms
│   ├── security-review.md              # Week 6 contract security self-review
│   └── openapi/                        # generated OpenAPI JSON: xleuth-api.json, xleuth-matching.json
│
├── data-ingestion/
│   ├── src/
│   │   ├── xleuth_ingestion/
│   │   │   ├── __init__.py
│   │   │   ├── __main__.py             # python -m xleuth_ingestion → poller.main()
│   │   │   ├── polymarket_client.py    # Gamma /markets, CLOB midpoint(s), Data API /live-volume wrappers
│   │   │   ├── event_map.py            # event_id → [conditionIds] dedup, drives /live-volume calls
│   │   │   ├── selection.py            # pure constituent filter (replaces planned liquidity_filter.py)
│   │   │   ├── vwap.py                 # sub-outcome VWAP + basket VWAP
│   │   │   ├── basket_builder.py       # TOP{N}-{MONTH} + DB-driven build_basket_from_params rules
│   │   │   ├── realized_fraction.py    # volume-weighted YES fraction for settlement
│   │   │   ├── storage.py              # TimescaleDB writes (index_prices, market_prices)
│   │   │   ├── redis_publisher.py      # xleuth:basket:{name}:price publish
│   │   │   └── poller.py               # scheduled ingestion loop (DB-first discovery)
│   ├── tests/
│   │   ├── test_ingestion_live.py      # hits real Polymarket API, per Week 1 verification prompt
│   │   ├── test_basket_lifecycle.py
│   │   └── test_realized_fraction.py
│   ├── .env.example
│   ├── requirements.txt
│   ├── pytest.ini
│   └── Dockerfile
│
├── backend-api/
│   ├── src/
│   │   ├── xleuth_api/
│   │   │   ├── __init__.py
│   │   │   ├── main.py                 # FastAPI app entrypoint
│   │   │   ├── db.py                   # asyncpg pool: users, transactions, faucet_claims + baskets
│   │   │   ├── chain.py                # read-only Web3: vault balances, positions, oracle price
│   │   │   ├── dependencies.py         # get_db / get_current_user (internal JWT) / get_chain_reader
│   │   │   ├── auth/
│   │   │   │   ├── __init__.py
│   │   │   │   └── dynamic_jwt.py      # Dynamic.xyz RS256 → internal HS256 (no SIWE; siwe.py/jwt.py removed)
│   │   │   ├── routes/
│   │   │   │   ├── auth.py             # POST /auth/verify, GET /auth/me
│   │   │   │   ├── baskets.py          # basket list, live price, history, constituents, candles
│   │   │   │   ├── accounts.py         # me, alias, tx history, portfolio summary
│   │   │   │   ├── faucet.py           # POST /faucet/claim (1000 MockUSDC, 24h cooldown)
│   │   │   │   └── websocket.py        # /ws/price/{basket} + /ws/orderbook/{basket} streaming
│   │   │   ├── models/
│   │   │   │   └── __init__.py         # empty — models live in shared/xleuth_shared/schemas/
│   ├── tests/                           # conftest + test_auth_flow/faucet_auth/websocket/tasks_15_16
│   ├── .env.example
│   ├── requirements.txt
│   └── Dockerfile
│
├── oracle-service/
│   ├── src/
│   │   ├── xleuth_oracle/
│   │   │   ├── __init__.py
│   │   │   ├── __main__.py
│   │   │   ├── main.py                 # run_cycle + loop_forever (15s push loop)
│   │   │   ├── config.py               # OracleConfig.load(): rpc, oracle addr, signer key, staleness
│   │   │   ├── price_source.py         # Postgres-first, Redis-fallback scaled_price read
│   │   │   ├── basket_source.py        # DB-first active-basket discovery (env fallback)
│   │   │   ├── signing.py              # EIP-712 PriceUpdate/SettleBasket signing + price_to_scale
│   │   │   └── pusher.py               # push loop with retry/backoff to chain
│   ├── tests/                           # test_signing.py, test_config.py
│   ├── .env.example
│   ├── requirements.txt
│   └── Dockerfile
│
├── matching-engine/
│   ├── src/
│   │   ├── xleuth_matching/
│   │   │   ├── __init__.py
│   │   │   ├── config.py              # env config: chain, risk params, trader keys
│   │   │   ├── orderbook.py           # extends order-matching (price-time priority books)
│   │   │   ├── margin_check.py        # reads on-chain margin/oracle state before accepting orders
│   │   │   ├── settlement.py          # submits matched fills to PositionManager (trader-signed)
│   │   │   ├── basket_source.py       # DB-first basket registry (60s TTL, env fallback)
│   │   │   ├── api.py                 # FastAPI service: place/cancel/query/book/positions, JWT auth
│   │   │   └── main.py                # uvicorn entry point
│   ├── tests/                         # test_orderbook/margin_check/settlement/api + test_matching_live/test_e2e_live (Amoy)
│   ├── .env.example
│   ├── requirements.txt
│   └── Dockerfile
│
├── contracts/
│   ├── foundry.toml
│   ├── src/
│   │   ├── CollateralVault.sol
│   │   ├── PositionManager.sol
│   │   ├── IndexOracleConsumer.sol
│   │   ├── SettlementEngine.sol
│   │   └── MockUSDC.sol               # 6dp test faucet token
│   ├── script/
│   │   ├── DeployAmoy.s.sol           # full stack deploy
│   │   ├── DeployMockUSDC.s.sol
│   │   ├── DeploySettlementEngine.s.sol
│   │   ├── ConfigureBaskets.s.sol     # seed oracle prices
│   │   ├── SettleBasket.s.sol         # manual settlement relay
│   │   ├── OpenPosition.s.sol         # demo long
│   │   ├── RedeployCore.s.sol
│   │   ├── RedeployWeek5.s.sol        # fresh vault+PM with updatePosition
│   │   ├── UpgradeAmoy.s.sol          # gas-lean: reuse vault+oracle, fresh PM+engine
│   │   └── MintMockUSDCReserve.s.sol
│   ├── test/
│   │   ├── CollateralVault.t.sol
│   │   ├── PositionManager.t.sol
│   │   ├── IndexOracleConsumer.t.sol
│   │   ├── SettlementEngine.t.sol
│   │   ├── ConfigureBaskets.t.sol
│   │   └── OracleServiceCrossCheck.t.sol
│   ├── lib/                            # forge install dependencies (OpenZeppelin, forge-std)
│   └── .env.example
│
├── shared/
│   ├── xleuth_shared/
│   │   ├── schemas/                    # Pydantic models: auth/accounts/baskets/orders/faucet/websocket
│   │   ├── auth/                       # dynamic_jwt.py (RS256) + internal_jwt.py (HS256)
│   │   ├── baskets.py                  # naming/slug/lifecycle source of truth (keccak ids)
│   │   ├── basket_lifecycle.py         # legacy ACTIVE_BASKETS template expansion
│   │   ├── db_baskets.py               # baskets + basket_events asyncpg layer
│   │   ├── rate_limit.py               # shared RateLimitMiddleware
│   │   └── constants.py                # INDEX_PRICE_SCALE=100
│   ├── tests/                          # test_baskets.py, test_rate_limit.py
│   └── requirements.txt
│
├── admin-cli/                          # only supported basket admin (no admin HTTP endpoint)
│   ├── src/xleuth_admin/
│   │   ├── cli.py                      # create/list/show/register/close/settle/reconcile
│   │   ├── chain.py                    # setBasketExpiry relay + expiryOf/latestPrice reads
│   │   └── selection_runner.py         # live dry-run selection preview
│   ├── tests/test_basket_flows.py
│   └── requirements.txt
│
├── frontend/                           # React 18 SPA (Fusion Starter: Router 6, Vite, Tailwind, Radix)
│   ├── client/                         # / landing; /app and /market/:slug trading; /explore, /portfolio, /account, legal
│   ├── server/                         # Express stub (GET /api/ping, /api/demo only)
│   ├── shared/api.ts                   # DemoResponse leftover
│   ├── public/  index.html  vite.config.ts  tailwind.config.ts  netlify.toml
│   └── package.json                    # pnpm; dev/build/start/typecheck/test (vitest)
│
├── migrations/
│   ├── 001_baskets.sql                 # baskets + basket_events (reversible)
│   ├── 003_waitlist.sql                # public landing waitlist, idempotently ensured by backend-api
│   └── down/001_baskets.down.sql
│
├── infra/
│   └── scripts/
│       └── seed_baskets.py             # backfills live-basket rows, no fake price data
│
└── scripts/
    ├── check-baskets.sh                # bans hardcoded baskets / admin HTTP surface
    ├── check-bundle-secrets.sh         # frontend bundle secret scan (make check-bundle)
    ├── check-env-examples.sh           # env drift guard (make check-secrets, pre-commit hook)
    ├── check-links.sh                  # markdown link check (make check-links)
    └── build-sitemap.sh                # SEO sitemap build
```

