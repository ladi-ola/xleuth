FROM python:3.12-slim

WORKDIR /app

COPY oracle-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY oracle-service/src/xleuth_oracle/ /app/xleuth_oracle/
COPY shared/xleuth_shared/ /app/xleuth_shared/

ENV PYTHONPATH=/app

CMD ["python", "-m", "xleuth_oracle"]