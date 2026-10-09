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
3. **Testnet noindex default.** Per the plan defaults the whole site ships
   `noindex` until opened — indexed basket pages would contradict that.
4. **Thin-content risk.** Auto-generating `/baskets/<slug>` shells without
   constituents, methodology and real prices would be doorway pages.

Nothing half-baked was shipped: no placeholder basket pages, no fabricated
stats, no sitemap entries without a domain.

## What would make it viable

- [ ] Production backend URL recorded + reachable at build time.
- [ ] Prerender step (e.g. Vite SSG / Netlify edge) rendering `/baskets/<slug>`
  from the DB: name, expiry, constituents, current index value, methodology.
- [ ] Unique titles/descriptions from real fields, canonical slug URLs,
  accurate structured data, archived-vs-redirect handling for expired baskets,
  DB-driven sitemap entries (extend `scripts/build-sitemap.sh`).
- [ ] Flip `VITE_ROBOTS_CONTENT` to `index, follow` and re-verify with `curl`.
