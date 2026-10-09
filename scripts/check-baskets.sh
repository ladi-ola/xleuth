#!/usr/bin/env bash
#
# check-baskets.sh — CI/grep guardrail (PLAN.md "Guardrails against regression").
# Fails if basket names, month-based identifiers or market counts appear in
# config files or constants. Baskets are data (DB), not config.
#
# Allowed: docs/, tests/fixtures via CLI path, scripts that expand templates,
# the single naming function (shared/xleuth_shared/baskets.py), legacy
# lifecycle compat (shared/xleuth_shared/basket_lifecycle.py), and this file.
set -u

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$repo_root" ]; then
    echo "ERROR: not inside a git worktree." >&2
    exit 1
fi
cd "$repo_root" || exit 1

fail=0

# 1. Hardcoded TOP{N}-{MONTH} names in config VALUES (not # comments/docs).
if grep -rInE "^[^#]*TOP[0-9]+-(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)" \
    --include="*.yml" --include="*.yaml" --include=".env.example" \
    --include="Makefile" --include="Dockerfile" \
    . --exclude-dir=.git --exclude-dir=.venv --exclude-dir=node_modules \
    | grep -v "^./docs/" | grep -v "^./frontend/"; then
    echo "ERROR: hardcoded basket name in config above. Baskets live in the DB." >&2
    fail=1
fi

# 2. ACTIVE_BASKETS must not regain a hardcoded literal month list in examples.
if grep -rInE "^ACTIVE_BASKETS=.*(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)" \
    --include=".env.example" . --exclude-dir=.git --exclude-dir=.venv; then
    echo "ERROR: ACTIVE_BASKETS literal month list in .env.example (keep the TOP20-{MONTH} template during transition)." >&2
    fail=1
fi

# 3. New name-parsing outside the sanctioned modules (legacy lifecycle helper,
# the deprecated basket_builder wrapper kept for live templates, poller
# transition, tests).
if grep -rInE "parse_basket_name\(|extract_target_month\(" \
    --include="*.py" data-ingestion/src oracle-service/src matching-engine/src backend-api/src admin-cli/src \
    | grep -v "basket_lifecycle" | grep -v "basket_builder.py" | grep -v "poller.py" | grep -v "test"; then
    echo "ERROR: name-parsing outside shared/xleuth_shared/basket_lifecycle.py (use DB columns)." >&2
    fail=1
fi

if [ "$fail" -ne 0 ]; then
    echo "check-baskets: FAILED." >&2
    exit 1
fi
echo "check-baskets: OK."
