#!/usr/bin/env bash
#
# check-links.sh — task 14: fail on dangling internal route links in the
# frontend source and on missing local asset references.
set -u

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$repo_root" ]; then
    echo "ERROR: not inside a git worktree." >&2
    exit 1
fi
cd "$repo_root/frontend" || exit 1

fail=0

# 1. Every internal `to="/..."` / `navigate("...")` / `navigateTo("/...")`
#    target must be a route in client/App.tsx (or an anchor/hash).
routes="$(grep -oE '<Route path="[^"]*"' client/App.tsx | sed -E 's/<Route path="//; s/"//' | grep -v '^\*$' | sort -u)"
for target in $(grep -rhoE '(to|navigateTo|navigate)\("/[^"]*"' client/ --include="*.tsx" | grep -oE '"/[^"]*"' | tr -d '"' | sort -u); do
    base="${target%%\?*}"
    # Dynamic /market/:slug prefix covers any /market/<slug>.
    if [ "$base" != "/market" ] && [[ "$base" == /market/* ]]; then
        continue
    fi
    if ! echo "$routes" | grep -qxF "$base"; then
        echo "ERROR: link target '$target' has no route in client/App.tsx" >&2
        fail=1
    fi
done

# 2. Local asset refs (src="/...") must exist in public/.
for asset in $(grep -rhoE '(src|href)="/[^"]*\.(png|svg|ico|webmanifest|json)"' client/ index.html --include="*.tsx" --include="*.html" | grep -oE '"/[^"]*"' | tr -d '"' | sort -u); do
    if [ ! -f "public$asset" ]; then
        echo "ERROR: asset '$asset' referenced but missing in public/" >&2
        fail=1
    fi
done

if [ "$fail" -ne 0 ]; then
    echo "check-links: FAILED." >&2
    exit 1
fi
echo "check-links: OK."
