.PHONY: test run-ingestion up down

test:
	PYTHONPATH=data-ingestion/src .venv/bin/pytest data-ingestion/tests/ -v

run-ingestion:
	PYTHONPATH=data-ingestion/src .venv/bin/python -m xleuth_ingestion

up:
	docker compose up -d

down:
	docker compose down