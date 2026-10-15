# Build context is THIS service's directory (not the repo root). The deploy
# BuildService sets the context to the service folder, so every COPY path below
# must be relative to here. shared/xleuth_shared/ is vendored into this
# directory by scripts/sync-shared.sh.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/xleuth_ingestion/ /app/src/xleuth_ingestion/
COPY shared/xleuth_shared/ /app/xleuth_shared/

ENV PYTHONPATH=/app/src:/app

CMD ["python", "-m", "xleuth_ingestion"]
