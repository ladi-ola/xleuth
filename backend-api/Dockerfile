# The deploy BuildService has been observed to build this service with several
# different build contexts (the service folder, the repo root, and a
# service/shared subfolder), depending on how the service is configured. A bare
# `COPY requirements.txt .` only works for one of those.
#
# So: copy whatever context we were handed into /build-context, then locate the
# service payload inside it. This makes the image identical no matter which
# directory the platform uses as the context.
FROM python:3.12-slim

WORKDIR /app

COPY . /build-context/

RUN set -eux; \
    src=""; \
    for candidate in /build-context /build-context/backend-api; do \
      if [ -f "$candidate/requirements.txt" ] && [ -d "$candidate/src" ]; then \
        src="$candidate"; \
        break; \
      fi; \
    done; \
    if [ -z "$src" ]; then \
      echo "ERROR: could not locate requirements.txt + src/ under /build-context" >&2; \
      echo "Build context contained:" >&2; ls -la /build-context >&2; \
      exit 1; \
    fi; \
    echo "Using service payload from $src"; \
    cp "$src/requirements.txt" /app/requirements.txt; \
    mkdir -p /app/src; \
    cp -r "$src/src/." /app/src/; \
    if [ -d "$src/shared/xleuth_shared" ]; then \
      mkdir -p /app/xleuth_shared; \
      cp -r "$src/shared/xleuth_shared/." /app/xleuth_shared/; \
    elif [ -d /build-context/shared/xleuth_shared ]; then \
      mkdir -p /app/xleuth_shared; \
      cp -r /build-context/shared/xleuth_shared/. /app/xleuth_shared/; \
    fi; \
    test -f /app/xleuth_shared/__init__.py

RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONPATH=/app/src:/app

CMD ["sh", "-c", "uvicorn xleuth_api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]