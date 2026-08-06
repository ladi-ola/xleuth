.PHONY: test test-contracts test-api test-oracle test-matching test-all check-secrets install-hooks run-ingestion run-api run-oracle run-matching deploy-testnet deploy-upgrade deploy-config-baskets deploy-settle-basket deploy-open-position up down

test:
	PYTHONPATH=data-ingestion/src:shared .venv/bin/pytest data-ingestion/tests/ -v

test-contracts:
	cd contracts && forge test --gas-report

test-api:
	PYTHONPATH=backend-api/src:shared .venv/bin/pytest backend-api/tests/ -v

test-oracle:
	PYTHONPATH=oracle-service/src:shared .venv/bin/pytest oracle-service/tests/ -v

test-matching:
	PYTHONPATH=matching-engine/src:shared .venv/bin/pytest matching-engine/tests/ -v

test-all: test test-contracts test-api test-oracle test-matching

run-oracle:
	PYTHONPATH=oracle-service/src:shared .venv/bin/python -m xleuth_oracle

run-matching:
	PYTHONPATH=matching-engine/src:shared .venv/bin/uvicorn xleuth_matching.main:app --host 0.0.0.0 --port 8001


check-secrets:
	scripts/check-env-examples.sh

install-hooks:
	printf '#!/usr/bin/env bash\n"$$(git rev-parse --show-toplevel)/scripts/check-env-examples.sh" || exit 1\n' > .git/hooks/pre-commit
	chmod +x .git/hooks/pre-commit
	@echo "pre-commit hook installed."

run-ingestion:
	PYTHONPATH=data-ingestion/src:shared .venv/bin/python -m xleuth_ingestion

run-api:
	PYTHONPATH=backend-api/src:shared .venv/bin/uvicorn xleuth_api.main:app --reload --host 0.0.0.0 --port 8000

up:
	docker compose up -d

down:
	docker compose down

# ── Contracts (Week 3) ────────────────────────────────────────────────────
# Reads contracts/.env (gitignored); never hardcode RPC/key/addresses.
deploy-testnet:
	cd contracts && forge script script/DeployAmoy.s.sol:DeployAmoy \
		--rpc-url $$(grep '^RPC_URL=' .env | cut -d= -f2) \
		--private-key $$(grep '^DEPLOYER_PRIVATE_KEY=' .env | cut -d= -f2) \
		--broadcast

# Gas-lean upgrade of an existing Week-3 stack: fresh PositionManager +
# SettlementEngine, re-points the deployed vault, reuses the oracle consumer.
deploy-upgrade:
	cd contracts && forge script script/UpgradeAmoy.s.sol:UpgradeAmoy \
		--rpc-url $$(grep '^RPC_URL=' .env | cut -d= -f2) \
		--private-key $$(grep '^DEPLOYER_PRIVATE_KEY=' .env | cut -d= -f2) \
		--broadcast

deploy-config-baskets:
	cd contracts && forge script script/ConfigureBaskets.s.sol:ConfigureBaskets \
		--rpc-url $$(grep '^RPC_URL=' .env | cut -d= -f2) \
		--broadcast

deploy-settle-basket:
	cd contracts && forge script script/SettleBasket.s.sol:SettleBasket \
		--rpc-url $$(grep '^RPC_URL=' .env | cut -d= -f2) \
		--private-key $$(grep '^DEPLOYER_PRIVATE_KEY=' .env | cut -d= -f2) \
		--broadcast

deploy-open-position:
	cd contracts && forge script script/OpenPosition.s.sol:OpenPosition \
		--rpc-url $$(grep '^RPC_URL=' .env | cut -d= -f2) \
		--private-key $$(grep '^TRADER_PRIVATE_KEY=' .env | cut -d= -f2 || grep '^DEPLOYER_PRIVATE_KEY=' .env | cut -d= -f2) \
		--broadcast
