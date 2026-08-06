FROM python:3.12-slim

WORKDIR /app

COPY matching-engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY matching-engine/src/xleuth_matching/ /app/xleuth_matching/
COPY shared/xleuth_shared/ /app/xleuth_shared/

ENV PYTHONPATH=/app

CMD ["uvicorn", "xleuth_matching.main:app", "--host", "0.0.0.0", "--port", "8001"]
