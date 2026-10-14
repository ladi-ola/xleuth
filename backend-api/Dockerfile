FROM python:3.12-slim

WORKDIR /app

COPY backend-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend-api/src/xleuth_api/ /app/xleuth_api/

ENV PYTHONPATH=/app

CMD ["sh", "-c", "uvicorn xleuth_api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
