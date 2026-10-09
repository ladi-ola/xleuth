# Analytics — Xleuth frontend (`client/lib/analytics.ts`)

Privacy-friendly, cookieless, **off by default**. No SDK, no fingerprinting.

## Enabling (operator)

Set both env vars, then rebuild:

```bash
VITE_ANALYTICS_URL=https://<your-collector>/api/send
VITE_ANALYTICS_SITE=<website-id-or-domain>
```

Any self-hosted collector accepting `{website, name, url, referrer}` JSON works
(Umami-compatible shape; adapt the endpoint, not the client). No paid service
was added — hosting the collector is the operator's choice.

## Events (names only — never any properties)

| Event | When | Notes |
|---|---|---|
| `page_view:<path>` | Every route change | Path only, e.g. `page_view:/explore` |
| `wallet_auth_opened` | Sign-in button clicked | Started, not completed |
| `deposit_submitted` | Faucet claim clicked | Test-USDC deposit signal |
| `order_submitted` | Trade modal submitted | Placement signal, not fill confirmation |

**Never sent:** wallet addresses, signatures, tokens, balances, sizes,
prices, or any identifying/financial data — `track()` accepts a name string
only, so properties cannot be attached by construction.

## Consent / DNT

- Nothing fires unless both env vars are set (default build sends zero requests).
- `Do Not Track` (`navigator.doNotTrack === '1'`) and Global Privacy Control
  suppress all events automatically.
- Manual opt-out: `localStorage.setItem('xleuth-analytics-optout', '1')`.
- The in-app cookie notice (strictly-necessary-storage only) links the privacy
  policy, which documents the above. No consent wall: no non-essential storage
  exists.

## Verification

With env set, open DevTools → Network, navigate/click, and confirm POSTs to
`VITE_ANALYTICS_URL` with `{website, name, url}` only. With env unset (default
build), confirm zero analytics requests. (Production-browser check still owed —
no browser in this environment; see final report.)
