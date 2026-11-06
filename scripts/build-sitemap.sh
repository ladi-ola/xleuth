#!/usr/bin/env bash
#
# build-sitemap.sh — task 9: generate frontend/public/sitemap.xml.
# Sitemap URLs must be absolute https, so this needs the production URL:
#
#   ./scripts/build-sitemap.sh https://<confirmed-production-domain>
#
# or set VITE_PUBLIC_SITE_URL in frontend/.env (same value feeds the
# canonical/OG tags). With no URL it exits 0 without writing. Only / is
# indexable; the other SPA paths have Vercel noindex headers.
set -u

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$repo_root" ]; then
    echo "ERROR: not inside a git worktree." >&2
    exit 1
fi

site="${1:-}"
if [ -z "$site" ]; then
    site="$(grep -E '^VITE_PUBLIC_SITE_URL=' "$repo_root/frontend/.env" 2>/dev/null | cut -d= -f2- || true)"
fi
site="${site%/}"

if [ -z "$site" ]; then
    echo "build-sitemap: no site URL (arg or VITE_PUBLIC_SITE_URL); skipping sitemap."
    exit 0
fi

case "$site" in
    https://*) ;;
    *) echo "ERROR: site URL must be absolute https, got '$site'." >&2; exit 1 ;;
esac

today="$(date -u +%Y-%m-%d)"
out="$repo_root/frontend/public/sitemap.xml"

{
    echo '<?xml version="1.0" encoding="UTF-8"?>'
    echo '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    echo "  <url><loc>${site}/</loc><lastmod>${today}</lastmod><changefreq>monthly</changefreq></url>"
    echo '</urlset>'
} > "$out"

echo "build-sitemap: wrote $out for $site"
