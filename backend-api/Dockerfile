FROM python:3.12-slim

WORKDIR /app

COPY backend-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend-api/src/xleuth_api/ /app/xleuth_api/
COPY shared/xleuth_shared/ /app/xleuth_shared/

ENV PYTHONPATH=/app

CMD ["uvicorn", "xleuth_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
