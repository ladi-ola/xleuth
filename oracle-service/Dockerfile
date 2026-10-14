FROM python:3.12-slim

WORKDIR /app

COPY oracle-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY oracle-service/src/xleuth_oracle/ /app/xleuth_oracle/

ENV PYTHONPATH=/app/xleuth_shared

CMD ["python", "-m", "xleuth_oracle"]
