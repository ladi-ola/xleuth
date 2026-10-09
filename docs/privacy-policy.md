# Privacy Policy — Xleuth (testnet)

> Draft from the real data-flow audit (2026-10-09). Facts the codebase cannot
> know are marked `[[FILL: ...]]` — fill them before presenting this as final.
> This is not legal advice.
> Effective date: [[FILL: effective date]].
> Operator: [[FILL: operator legal name]], contact: [[FILL: contact email]].
> Jurisdiction: [[FILL: jurisdiction]].

## 1. Who we are

[[FILL: operator legal name]] operates Xleuth, a testnet-only leveraged trading
interface for prediction-market index baskets.

## 2. Testnet notice

Xleuth runs on the **Polygon Amoy testnet (chain id 80002)** with test USDC
that has **no monetary value**. Testnet data — including balances, positions
and history — **may be reset at any time** without notice.

## 3. What we collect

| Data | Where it lives | Lifetime |
|---|---|---|
| Wallet address (lowercased) + display alias | App Postgres (`users` table), via `POST /auth/verify` upsert | Until testnet reset; alias removable on request |
| Balances, realized/unrealized PnL | App Postgres (`users`) + on-chain vault | Same as above; on-chain copy permanent (see §5) |
| Orders, positions, fills, tx history | App Postgres (`transactions`), matching-engine books, on-chain | Same as above |
| Faucet last-claim timestamp | App Postgres (`faucet_claims`) | Until reset |
| Dynamic sign-in token | Sent once to `POST /auth/verify`, verified against Dynamic JWKS, never stored | Single request |
| Internal app session JWT (HS256) | **In memory only** (frontend `tokenState`; `Authorization: Bearer` header). Never in cookies or localStorage | 60 min (`JWT_EXPIRY_MINUTES`), then re-verify |
| Sidebar collapse preference | One functional cookie `sidebar:state=true/false`, `Path=/`, 7 days, `SameSite=Lax` (+`Secure` on HTTPS) | 7 days |
| IPs, user agents | Seen transiently by our API/RPC hosts and third parties below (standard access logs); **we store no IP/user-agent columns** and log no request bodies, tokens or signatures | Host log retention applies |

We collect **no** passwords, emails, names, or payment details. The only
free-form personal data is the optional alias.

## 4. How we use it

Authentication, balance/position accounting, faucet cooldown enforcement
(24h), order matching and on-chain settlement, and strictly-necessary
product operation. No marketing use, no sale of data.

## 5. Blockchain data is public and immutable

Everything written to Polygon Amoy — wallet addresses, deposits/withdrawals,
position opens/updates/closes/liquidations/settlements, oracle price pushes,
faucet transfers, tx hashes — is **publicly queryable and permanent**. It
**cannot be deleted**, including by us. Do not use an address you need to
keep private.

## 6. Third parties (named, from the audit)

| Party | What they see | Why |
|---|---|---|
| Dynamic (`app.dynamic.xyz`, env `938a93a5-…`) | Wallet address, sign-in flow, IP | Wallet auth + embedded wallets |
| Google Fonts (`fonts.googleapis.com`) | IP / user agent | Typeface (`Poppins`) |
| Builder.io (`api.builder.io`) | IP / user agent | Logo image host |
| Alchemy demo RPC (`polygon-amoy.g.alchemy.com/v2/demo`) | RPC requests + IP | Chain reads (replace with own key in prod) |
| Polygon Amoy public RPC (`publicnode.com`) | RPC requests (balances, positions, prices) + IP | Chain reads/writes |
| Polymarket public APIs (Gamma/CLOB/data-api) | Market/token/event ids only — **no wallet or auth data** | Index computation (server-side) |
| Hosting/RPC/DB providers | Standard access/error logs | Infrastructure |

No first-party product analytics SDK, no error tracker, no ads, no social
embeds ship in the app.

## 7. Cookies and local storage

Strictly necessary only (§3). Cookieless usage analytics **only if** the
operator sets `VITE_ANALYTICS_URL` + `VITE_ANALYTICS_SITE` (default: off —
nothing fires). Do Not Track and Global Privacy Control are respected.
Opt-out any time: enable DNT/GPC, or set `xleuth-analytics-optout=1` in
localStorage. No consent wall is needed because no non-essential storage
exists; the in-app notice links here.

## 8. Retention

App-database records persist until a testnet reset. Request alias/app-record
removal at [[FILL: contact email]]. Backups, if any, follow [[FILL: backup
retention]]. On-chain data is retained forever by the chain.

## 9. Security measures (only what exists)

TLS in transit (HTTPS/WSS in production); JWTs short-lived (60 min) and
never logged; private keys never leave the operator's server env; no secrets
in the frontend bundle (CI-checked); source maps disabled; security headers
(HSTS, nosniff, Referrer-Policy, frame DENY, report-only CSP) at the host.

## 10. Your rights and honest limits

Request access/correction/deletion of **app-held** data at [[FILL: contact
email]]. Limits: on-chain records cannot be altered or deleted; chain-indexer
copies are outside our control; testnet resets may delete app data without
individual notice.

## 11. Children

18+ only. Not directed at children; do not use if under 18.

## 12. International transfers

Data touches infrastructure/third parties in [[FILL: hosting countries]]
and the globally replicated Amoy chain. By using the testnet you consent to
that transfer.

## 13. Changes

Material changes will be noted here with a new effective date. Continued use
after changes take effect constitutes acceptance.
