.PHONY: test test-contracts test-api test-oracle test-matching test-e2e test-all test-shared test-admin check-secrets install-hooks run-ingestion run-api run-oracle run-matching deploy-testnet deploy-upgrade deploy-config-baskets deploy-settle-basket deploy-open-position up down basket-create basket-list basket-show basket-register basket-close basket-settle basket-reconcile check-bundle check-links

test:
	PYTHONPATH=data-ingestion/src:shared .venv/bin/pytest data-ingestion/tests/ -v

test-contracts:
	cd contracts && forge test --gas-report

test-api:
	PYTHONPATH=backend-api/src:shared .venv/bin/pytest backend-api/tests/ -v

test-oracle:
	PYTHONPATH=oracle-service/src:shared .venv/bin/pytest oracle-service/tests/ -v

test-matching:
	PYTHONPATH=matching-engine/src:shared .venv/bin/pytest matching-engine/tests/ -v --ignore=matching-engine/tests/test_e2e_live.py

# Week-6 full end-to-end live test (real Polymarket data -> Amoy settlement).
# Requires live network access and the deployed Amoy contracts; the dedicated
# test basket is settled permanently, so run once per basket name.
test-e2e:
	PYTHONPATH=data-ingestion/src:oracle-service/src:matching-engine/src:shared .venv/bin/pytest matching-engine/tests/test_e2e_live.py -v -s

test-all: test test-contracts test-api test-oracle test-matching test-shared

test-shared:
	PYTHONPATH=shared python3 -m pytest shared/tests/ -v

# ── Basket admin CLI (PLAN.md: no new HTTP surface) ────────────────────
# Usage: make basket-create THEME=TOP COUNT=20 WINDOW_START=2026-10-01T00:00:00Z EXPIRY=2026-10-31T23:59:59Z [DRY=1] [RULES=rules.json]
ADMIN_PY=PYTHONPATH=admin-cli/src:data-ingestion/src:shared python3 -m xleuth_admin.cli

basket-create:
	$(ADMIN_PY) create --theme $(THEME) --count $(COUNT) --window-start $(WINDOW_START) --expiry $(EXPIRY) $(if $(RULES),--rules-file $(RULES)) $(if $(DRY),--dry-run)

basket-list:
	$(ADMIN_PY) list $(if $(STATUS),--status $(STATUS))

basket-show:
	$(ADMIN_PY) show $(SLUG)

basket-register:
	$(ADMIN_PY) register $(SLUG)

basket-close:
	$(ADMIN_PY) close $(SLUG)

basket-settle:
	$(ADMIN_PY) settle $(SLUG)

basket-reconcile:
	$(ADMIN_PY) reconcile $(SLUG) $(if $(REPAIR),--repair)

run-oracle:
	PYTHONPATH=oracle-service/src:shared .venv/bin/python -m xleuth_oracle

run-matching:
	PYTHONPATH=matching-engine/src:shared .venv/bin/uvicorn xleuth_matching.main:app --host 0.0.0.0 --port 8001


check-secrets:
	scripts/check-env-examples.sh

check-baskets:
	scripts/check-baskets.sh

check-bundle:
	scripts/check-bundle-secrets.sh

check-links:
	scripts/check-links.sh

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
