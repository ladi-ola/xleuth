.PHONY: test run-ingestion run-api up down check-secrets install-hooks

test:
	PYTHONPATH=data-ingestion/src .venv/bin/pytest data-ingestion/tests/ -v

test-api:
	PYTHONPATH=backend-api/src:shared .venv/bin/pytest backend-api/tests/ -v

test-all: test test-api

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
