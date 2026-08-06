## 3. Repository Structure

```
xleuth/
├── .env.example                        # union of all service .env.example files, for docker-compose
├── .gitignore
├── README.md
├── LICENSE
├── docker-compose.yml
├── docker-compose.override.yml.example
├── Makefile                            # common tasks: make up, make test, make deploy-testnet
│
├── docs/
│   ├── architecture.md                 # module boundaries, data flow diagram (Week 6 deliverable)
│   ├── api-contract.md                 # generated from FastAPI OpenAPI spec, for frontend handoff
│   ├── security-review.md              # Week 6 self-review checklist output
│   └── scope.md                        # what's live vs. simulated vs. explicitly descoped
│
├── data-ingestion/
│   ├── src/
│   │   ├── xleuth_ingestion/
│   │   │   ├── __init__.py
│   │   │   ├── polymarket_client.py    # Gamma /markets, CLOB price/book, Data API /live-volume wrappers
│   │   │   ├── event_map.py            # event_id → [conditionIds] dedup, drives /live-volume calls
│   │   │   ├── liquidity_filter.py
│   │   │   ├── vwap.py                 # sub-outcome VWAP + basket VWAP
│   │   │   ├── basket_builder.py       # TOP{N}-{MONTH} construction rules
│   │   │   ├── storage.py              # TimescaleDB writes
│   │   │   └── poller.py               # scheduled ingestion loop
│   ├── tests/
│   │   └── test_ingestion_live.py      # hits real Polymarket API, per Week 1 verification prompt
│   ├── .env.example
│   ├── requirements.txt
│   └── Dockerfile
│
├── backend-api/
│   ├── src/
│   │   ├── xleuth_api/
│   │   │   ├── __init__.py
│   │   │   ├── main.py                 # FastAPI app entrypoint
│   │   │   ├── auth/
│   │   │   │   ├── siwe.py             # EIP-712/SIWE nonce + signature verification
│   │   │   │   └── jwt.py
│   │   │   ├── routes/
│   │   │   │   ├── baskets.py          # basket list, live price, history, constituents
│   │   │   │   ├── accounts.py         # balance, PnL, alias, tx history
│   │   │   │   └── websocket.py        # live price + order book streaming
│   │   │   ├── models/                 # SQLAlchemy models: users, transactions
│   │   │   └── db.py
│   ├── tests/
│   ├── .env.example
│   ├── requirements.txt
│   └── Dockerfile
│
├── oracle-service/
│   ├── src/
│   │   ├── xleuth_oracle/
│   │   │   ├── __init__.py
│   │   │   ├── price_reader.py         # reads latest index price from ingestion/DB
│   │   │   ├── signer.py               # signs price updates with oracle key
│   │   │   └── pusher.py               # push loop with retry/backoff to chain
│   ├── tests/
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
│   │   │   ├── api.py                 # FastAPI service: place/cancel/query/book, JWT auth
│   │   │   └── main.py                # uvicorn entry point
│   ├── tests/                         # 45 unit + 2 live Amoy integration tests
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
│   │   └── SettlementEngine.sol
│   ├── script/
│   │   ├── DeployAmoy.s.sol
│   │   └── ConfigureBaskets.s.sol
│   ├── test/
│   │   ├── CollateralVault.t.sol
│   │   ├── PositionManager.t.sol
│   │   ├── IndexOracleConsumer.t.sol
│   │   └── SettlementEngine.t.sol
│   ├── lib/                            # forge install dependencies (OpenZeppelin, etc.)
│   └── .env.example
│
├── shared/
│   ├── xleuth_shared/
│   │   ├── schemas/                    # Pydantic models shared across services
│   │   ├── abis/                       # exported contract ABIs, consumed by backend/matching-engine
│   │   └── constants.py
│   └── requirements.txt
│
├── infra/
│   ├── docker/                         # any additional per-service Docker assets
│   ├── scripts/
│   │   ├── setup_local_env.sh
│   │   └── seed_baskets.py             # creates initial ACTIVE_BASKETS rows, no fake price data
│   └── ci/
│       └── github-actions.yml          # test-on-push for all services (optional, add if time allows)
│
└── scripts/
    └── dev.sh                           # one-command local bring-up for demoing to early adopters
```

