.PHONY: test test-contracts test-api test-all check-secrets install-hooks run-ingestion run-api deploy-testnet deploy-config-baskets up down

test:
	PYTHONPATH=data-ingestion/src .venv/bin/pytest data-ingestion/tests/ -v

test-contracts:
	cd contracts && forge test --gas-report

test-api:
	PYTHONPATH=backend-api/src:shared .venv/bin/pytest backend-api/tests/ -v

test-all: test test-contracts test-api

check-secrets:
	scripts/check-env-examples.sh

install-hooks:
	printf '#!/usr/bin/env bash\n"$$(git rev-parse --show-toplevel)/scripts/check-env-examples.sh" || exit 1\n' > .git/hooks/pre-commit
	chmod +x .git/hooks/pre-commit
	@echo "pre-commit hook installed."

run-ingestion:
	PYTHONPATH=data-ingestion/src .venv/bin/python -m xleuth_ingestion

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

deploy-config-baskets:
	cd contracts && forge script script/ConfigureBaskets.s.sol:ConfigureBaskets \
		--rpc-url $$(grep '^RPC_URL=' .env | cut -d= -f2) \
		--broadcast
