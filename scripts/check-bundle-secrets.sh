#!/usr/bin/env bash
#
# check-bundle-secrets.sh — task 3: fail if secret-looking strings appear in
# the production frontend bundle (frontend/dist/spa).
#
# Known-benign hits are excluded: Dynamic SDK i18n strings for its embedded
# wallet export UI ("EXPORT_PRIVATE_KEY", "private_key_title", ...). Those
# contain no key material (verified 2026-10-09: context is UI copy only).
# If this script fails on a NEW hit, assume exposure and rotate the secret.
set -u

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$repo_root" ]; then
    echo "ERROR: not inside a git worktree." >&2
    exit 1
fi
bundle_dir="$repo_root/frontend/dist/spa"

if [ ! -d "$bundle_dir" ]; then
    echo "check-bundle-secrets: no bundle at $bundle_dir (run a build first); skipping."
    exit 0
fi

fail=0

# 1. No source maps in production output.
if find "$bundle_dir" -name '*.map' -print -quit | grep -q .; then
    echo "ERROR: source map(s) found in production bundle:" >&2
    find "$bundle_dir" -name '*.map' >&2
    fail=1
fi

# 2. Hard secret patterns (real key material shapes). Note: bare 0x+64hex is
# NOT checked — every wallet library ships secp256k1 curve constants and
# bytecode that match it. Instead we match assignment-shaped leaks.
blocklist='BEGIN [A-Z ]*PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|sk-(live|test)-[A-Za-z0-9_-]{16,}|xox[baprs]-[0-9A-Za-z-]{10,}|AIza[0-9A-Za-z_-]{30,}|DATABASE_URL=postgres|REDIS_URL=redis://[^l]|JWT_SECRET=[^c]|private[_-]?key.{0,30}0x[0-9a-fA-F]{64}|0x[0-9a-fA-F]{64}.{0,30}private[_-]?key'
hits="$(grep -rInoE "$blocklist" "$bundle_dir" 2>/dev/null | grep -v -E 'EXPORT_PRIVATE_KEY|private_key_title|InvalidPrivateKeyFormat|copy_private_key|dyn_embedded_reveal|prompt_for_export|back up wallet key' || true)"
if [ -n "$hits" ]; then
    echo "ERROR: secret-looking strings in production bundle:" >&2
    echo "$hits" >&2
    fail=1
fi

if [ "$fail" -ne 0 ]; then
    echo "check-bundle-secrets: FAILED." >&2
    exit 1
fi
echo "check-bundle-secrets: OK."
