# Programmatic SEO evaluation (task 19) — verdict: NOT viable tonight

Evaluated honestly against the task's own bar ("only where each page has
real, unique, useful data"; "do not fabricate statistics").

## Why not tonight

1. **No prerender/SSR pipeline.** The app is a client-rendered SPA served via
   a `200` rewrite. Per-page meta/OG tags injected by JS are invisible to
   no-JS crawlers (documented in `client/hooks/use-page-meta.ts`). Building
   per-basket static pages needs a prerender step that does not exist.
2. **No build-time data access.** Basket content lives in the production
   Postgres (`baskets` table + `index_prices`), unreachable from the static
   build (browser calls the APIs directly; no prod backend URL is even
   recorded in the repo).
3. **Landing-only indexing.** `/` is indexable; non-root SPA routes are
    `noindex` via Vercel headers. Indexed basket pages would need their own
    unique, crawler-visible content.
4. **Thin-content risk.** Auto-generating `/baskets/<slug>` shells without
   constituents, methodology and real prices would be doorway pages.

Nothing half-baked was shipped: no placeholder basket pages, no fabricated
stats, no sitemap entries without a domain.

## Landing-page indexing (Task 2)

The landing page at `/` has no robots meta restriction. Vercel's
`frontend/vercel.json` adds `X-Robots-Tag: noindex, nofollow` to every
non-root path, including `/app`, trading, legal and unknown SPA routes.
`robots.txt` allows crawlers to fetch those paths so they can see that header.
It does not advertise a sitemap until a production URL is confirmed.
`scripts/build-sitemap.sh` can generate a root-only sitemap after that URL is
confirmed, but the Vercel build does not currently run it. Crawlers still
need to execute JavaScript to see landing-page body content: this is a SPA,
not a prerendered page. Indexability is not a guarantee of search indexing.

After deployment, check actual Vercel responses (Vite preview does not apply
`vercel.json`):

```bash
curl -sSI "$DOMAIN/" | grep -i x-robots-tag  # expect no header
curl -sSI "$DOMAIN/app" | grep -i x-robots-tag  # expect noindex, nofollow
curl -sSI "$DOMAIN/unknown" | grep -i x-robots-tag  # expect noindex, nofollow
curl -s "$DOMAIN/robots.txt"  # no missing sitemap reference
```

## What would make it viable

- [ ] Production backend URL recorded + reachable at build time.
- [ ] Prerender step (e.g. Vite SSG / Netlify edge) rendering `/baskets/<slug>`
  from the DB: name, expiry, constituents, current index value, methodology.
- [ ] Unique titles/descriptions from real fields, canonical slug URLs,
  accurate structured data, archived-vs-redirect handling for expired baskets,
  DB-driven sitemap entries (extend `scripts/build-sitemap.sh`).
- [ ] Confirm a production site URL before generating a sitemap or canonical URL.
