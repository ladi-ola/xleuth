# HTTPS / hosting checklist — Xleuth frontend (task 4)

**Current frontend target: Vercel.** The Netlify-specific settings below are
legacy. For landing-page indexing and Vercel header checks, see
`docs/programmatic-seo.md`.

Netlify serves the static SPA over HTTPS by default (managed certificate +
auto-renewal). Verify each item in the Netlify dashboard + with `curl`
against the real domain (no production URL is recorded in the repo — fill it
in on first deploy).

## Dashboard (manual, once)

- [ ] Custom domain assigned; DNS points at Netlify.
- [ ] **Force HTTPS** on (automatic http→https 301).
- [ ] TLS certificate active with auto-renewal.
- [ ] `www` vs apex canonical chosen; the other redirects to it.

## Shipped in repo (code)

- `netlify.toml [[headers]]`: HSTS `max-age=2592000` (30 days, **no
  preload**), `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY`,
  `Content-Security-Policy-Report-Only` (see below).
- Mixed-content guard in code: `secureUrl()` upgrades `http://→https://` and
  `ws://→wss://` whenever the page itself is HTTPS (`client/lib/api/urls.ts`,
  applied to REST + WebSocket URLs). **Production env must still set**
  `VITE_BACKEND_API_URL`, `VITE_MATCHING_ENGINE_URL`, `VITE_BACKEND_WS_URL`
  to `https://`/`wss://` origins.
- Sidebar cookie: `SameSite=Lax`, `Secure` on HTTPS.
- Backend CORS: `CORS_ALLOWED_ORIGINS` must list the real `https://` origins
  (credentials mode — wildcards won't work).

## Raising HSTS later

1. Confirm a full quarter with no HTTP-only dependency (check CSP reports).
2. Raise to `max-age=31536000`, wait one cycle.
3. Only then consider `includeSubDomains` and preload submission
   (`hstspreload.org`) — preload is effectively irreversible short-term.

## Promoting the CSP to enforcing

The report-only policy allows `'self'`, Dynamic, Google Fonts, Builder.io
images, and `https:/wss:` connects. After watching reports with no
unexpected violations: rename to `Content-Security-Policy`, keep
`'unsafe-inline'` for styles (Tailwind) until audited, then tighten.

## curl verification (run against the real domain)

```bash
DOMAIN=https://app.example.com  # <-- fill in
curl -sSI "http://app.example.com/" | grep -i "^location"        # expect https 301
curl -sSI "$DOMAIN/" | grep -iE "strict-transport|content-security|x-content-type|x-frame|referrer"
curl -s "$DOMAIN/" | grep -oE "<title>[^<]*</title>|noindex|og:image[^>]*"
curl -s "$DOMAIN/robots.txt"
# No sitemap is shipped until a production URL is confirmed.
curl -sSI "$DOMAIN/does-not-exist" | head -1   # SPA rewrite: expect 200 (documented)
```

## Provider settings (manual)

- Dynamic dashboard (`app.dynamic.xyz`): allowlist the production origin;
  rotate `VITE_DYNAMIC_ENVIRONMENT_ID` if the current one ever leaks publicly.
- Alchemy: replace the `demo` RPC key with a restricted app key (domain
  allowlist) — code reads `VITE_CHAIN_RPC_URL` already.
