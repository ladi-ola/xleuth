FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY data-ingestion/src/ /app/src/
COPY shared/xleuth_shared/ /app/xleuth_shared/

ENV PYTHONPATH=/app/src:/app

CMD ["python", "-m", "xleuth_ingestion"]
