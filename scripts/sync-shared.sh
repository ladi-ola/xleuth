#!/usr/bin/env bash
# Vendor the shared package into every service directory.
#
# Why this exists: the deploy BuildService builds each service with that
# service's own directory as the build context, so `COPY shared/...` can never
# resolve — the shared package has to physically live inside the context.
# BuildKit does not follow symlinks that point outside the context either.
#
# Run this after editing shared/xleuth_shared/, then commit the result.
# `make check-shared-sync` (and shared/tests/test_vendored_shared.py) verify
# the copies have not drifted.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/shared/xleuth_shared"
SERVICES=(data-ingestion backend-api matching-engine oracle-service)

if [[ ! -d "$SRC" ]]; then
  echo "error: $SRC not found" >&2
  exit 1
fi

for service in "${SERVICES[@]}"; do
  dest="$ROOT/$service/shared/xleuth_shared"
  mkdir -p "$dest"
  # --delete keeps removed modules from lingering in a service copy.
  rsync -a --delete --exclude '__pycache__' --exclude '*.pyc' "$SRC/" "$dest/"
  echo "synced $service/shared/xleuth_shared"
done