# Order placement verification — 2026-11-06

## Outcome

**NOT DONE / NOT ACTIVATED.** The original live limit-order failure remains
reproduced. No accepted browser order, matched fill, or trade settlement has
been proven. Local source now contains staged signed-execution components,
explicit-window/Data API v2 ingestion changes, tests and documentation, but no
reviewed financial ledger, live endpoint integration, production journal,
deployment or hosted DB/index writes.

## Environment and evidence

- Frontend: https://www.xleuth.xyz
- Backend observed in browser: https://backend-api-9emj.onrender.com
- Matching observed in browser: https://matching-engine-u84s.onrender.com
- Browser sessions used: `xleuth-order-qa` (isolated task session).
- Normal Dynamic login succeeded. The supplied credentials are deliberately
  omitted here. `/auth/verify`, `/positions`, `/accounts/summary`: **200**.
- Basket list/price/candles/constituents/book requests and preflights: **200**.
- No console/page errors were captured for the failed order attempt.
- Hosted service logs were unavailable; no Render credentials were requested or used.

### First limit-order attempt

At `2026-11-06T04:49:46.705Z`, the real modal submitted:

```json
{
  "basket_name": "TOP20-DECEMBER",
  "side": "buy",
  "size": 1.064963,
  "leverage": 2,
  "order_type": "limit",
  "price": 9.39
}
```

Matching response: **422**:

```json
{"detail":"oracle_price_stale ({'age_seconds': 7703401, 'max_staleness_seconds': 300})"}
```

The modal closed; the page remained usable. No order ID or transaction hash
was returned. The transient toast was not preserved, so its exact live text
is not claimed as verified. Source currently maps this code to a readable
stale-feed message.

The same session's portfolio response:

```json
{
  "total_balance": 1000.0,
  "free_margin": 1000.0,
  "used_margin": 0.0,
  "unrealized_pnl": 0.0,
  "realized_pnl": 0.0,
  "vault_free": 1000.0,
  "wallet_balance": 0.0
}
```

### End-to-end trace and first break

`TradeModal` → `Markets.handleOrderSubmitted` → `buildOrder` → `usePlaceOrder`
→ internal-token exchange/cache → matching `POST /orders` → JWT dependency
→ `MarginCheck.validate` → **stale oracle rejection**.

The order did **not** reach the book, settlement bridge or on-chain writes.
The stale guard is correct and was not weakened. Later security failures
found in source/local proofs must not be misrepresented as live executions.

### Read-only chain observations

The root `.env` specifies localhost service settings but these Amoy contracts:

| Contract | Address |
|---|---|
| Vault | `0x6dbeEb6a5bE0cD63159b1dBD5525dE125A1CECef` |
| PositionManager | `0x65e2687284c64576d2B7Cd55393163Fb9f6871ef` |
| Oracle | `0xd394B8A5dace5EB22933A2a0DCE1C82c1Eb70cd2` |
| SettlementEngine | `0x68aa3697b1783cb671c575D01C5622c2FA8570e8` |
| Test USDC | `0xc8783E02f3EE944BdE2990DbcDFefbe8adc3e86D` |

RPC `chain_id` was **80002**. All addresses have code. The four core runtime
instruction streams matched local Foundry build artifacts after masking
immutable references and stripping compiler metadata. This is not an
independent deployment audit or confirmation of hosted environment variables.

Legacy IDs were read as `keccak(NAME)`:

| Basket | Oracle `(price,timestamp)` | Settlement expiry | `isSettled` |
|---|---|---|---|
| TOP20-DECEMBER | `(4,1786237186)` | `1786237222` (2026-08-09 01:00:22 UTC) | true |
| TOP20-NOVEMBER | `(1,1792734581)` | `1786238371` | true |
| TOP20-OCTOBER | `(33,1792734597)` | `1786237466` | true |

At `04:57 UTC`, public API ingestion snapshots for November and December were
current and both were labelled `active`, `is_tradeable=true`; their `slug`,
`expiry_at`, and `onchain_index_id` were null. December's DB price was about
9.400 while its stale chain price was 4. **Ingestion is operating; oracle
freshness and lifecycle disagree with the live display.** Worker deployment
and failure reasons still require owner logs.

Screenshots outside the repository:
`/tmp/opencode/xleuth-order-qa/portfolio.png` and
`/tmp/opencode/xleuth-order-qa/explore.png`, plus `market-chart.png` in that
directory. Sanitized observed order/portfolio request bodies and responses are
in `sanitized-requests.json` there (auth requests/headers excluded). No
auth-state/HAR files containing credentials were written into the repository.

## Edge-case matrix

This matrix describes **browser acceptance**, not local security-test results.

| Case | Result | Evidence / limitation |
|---|---|---|
| Normal email/code login | PASS | Connected-wallet UI and `/auth/verify` 200. |
| Basic limit buy accepted/resting | FAIL | Actual payload above → stale-oracle 422. |
| Limit sell | NOT-TESTABLE | Healthy execution preconditions not established. |
| Market buy / sell | NOT-TESTABLE | Oracle/lifecycle/settlement blockers; no FOK execution claimed. |
| Stop buy / sell | NOT-TESTABLE | Same blockers; local trigger crash independently reproduced. |
| SL/TP attach / edit / cancel / OCO | NOT-TESTABLE | No verified open browser position. |
| Leverage 1x, 2x, 3x, 4x, 5x | NOT-TESTABLE | 2x request observed, but acceptance/each extreme unproven. |
| Exact / just-short collateral at max leverage | NOT-TESTABLE | No healthy settlement environment. |
| Size/price zero / negative / below min | NOT-TESTABLE | Not exercised through browser in this blocked pass. |
| Above maximum / excessive decimals / tiny / huge / sane price bounds | NOT-TESTABLE | Bounds/precision require specification; no invented values. |
| Insufficient / zero balance, never claimed | NOT-TESTABLE | Supplied account already has 1,000 vault USDC; second account not provided. |
| Faucet / first-time vault funding | NOT-TESTABLE | No extra claim made for already-funded account; no signer operations performed. |
| Slippage guard hit | NOT-TESTABLE | Valid tradable basket and counterparties unavailable. |
| FOK insufficient liquidity / empty book | NOT-TESTABLE | Cannot reach execution past stale-price gate. |
| Resting limit / partial / full fill / cancel | NOT-TESTABLE | No accepted order ID. |
| Self-trade / crossing / multiple orders at one price | NOT-TESTABLE | Accepted-order and counterparty prerequisites unavailable. |
| Expired / resolved / upcoming / unregistered basket rejection | NOT-TESTABLE | Chain/API drift observed read-only; correct UI rejection paths not swept. |
| Stale oracle rejected | PASS | Real 422 with `oracle_price_stale`; exact toast not preserved. |
| Signed-out trade attempt | NOT-TESTABLE | Signed-in session tested; no separate signed-out browser sweep. |
| Expired / invalid session mid-order | NOT-TESTABLE | No tokens modified or auth bypass attempted. |
| Account switch | NOT-TESTABLE | No second test account; local cache vulnerability reproduced. |
| Refresh during in-flight order | NOT-TESTABLE | No healthy acceptance flow. |
| Double submit | NOT-TESTABLE | Browser sweep blocked; local concurrent-idempotency failure reproduced. |
| Slow / failed network; cold-start timeout/retry | NOT-TESTABLE | Services eventually returned 200; controlled browser failure sweep not run. |
| Websocket drop/reconnect | NOT-TESTABLE | Not exercised; source review found streaming wiring gaps. |
| Post-trade Portfolio orders/positions/summary/margin | NOT-TESTABLE | Portfolio loads, but no accepted trade to reconcile. |
| All rejection codes readable | NOT-TESTABLE | Source audit found missing/misclassified cases; exhaustive browser proof pending. |
| Price/delta formatting after trade | NOT-TESTABLE | Baseline chart displays 3 decimals; no post-trade verification. |
| Withdraw remains disabled | PASS | Disabled button observed on live Portfolio. |
| January 2027 preview | PASS (read-only) | `top20-2027-01`, 20/20 selected, v2 taker volume 20/20, price 5.983, `ready_for_registration=true`, no warnings. Not a DB draft, registration or trading approval. |
| Polymarket Data API v2 | PASS (read-only) | `/v2/live-volume?event_id=73130` returned 200 and `data.conditions[].taker_volume`; old v1 endpoint returned 410 retired. |
| V2 Solidity gateway | PASS (local only) | 31 tests including digest vector, atomic rollback, multi-maker FOK, intent binding, bounds, EOA/ERC-1271 and replay/cancel. Not deployed. |
| V2 Python relay | PASS (local only) | 27 synthetic RPC/journal tests for pending reconciliation, no-resubmit, transaction/event evidence and chain checks. Production journal absent. |
| V2 shared authorization | PASS (local only) | 42 tests; digest vector matches TypeScript and Solidity. Not wired to `/orders`. |
| Post-change public browser regression | PASS (unauthenticated) | Fresh isolated session loaded Markets/chart controls and Explore cards; public backend price/chart/book/constituent reads returned 200; no browser errors. Portfolio correctly showed “Sign in to see your portfolio.” Authenticated login/order regression is not re-tested in this fresh session. |

## Tests and local proof evidence

Baseline commands from Makefile/package scripts were attempted. The checked-in
`.venv/bin/pytest`, bare `pnpm`, and bare `forge` were unavailable. Testing used
installed `python3 -m pytest`, `corepack pnpm`, and the official npm-distributed
Foundry binary from the external npm cache. No live key-using suites ran.

| Suite / check | Result |
|---|---|
| Matching, excluding both live suites | 113 passed, 1 warning. |
| Contracts | 129 passed, 0 failed (includes 31 gateway tests and existing/evidence suites). |
| Frontend | 93 passed; TypeScript check passed. |
| Shared | 67 passed. |
| Oracle | 22 passed (including timestamp rejection/fresh fallback regressions). |
| Backend | 45 passed, 1 warning. |
| Ingestion, excluding live suite | 36 passed. |
| Admin, all tests with imported source packages on PYTHONPATH | 14 passed. |
| Combined admin/backend/oracle rerun | 81 passed, 1 warning. |
| Env example secret guard | Passed (`make check-secrets`). |
| Link checker | FAIL (pre-existing checker drift) | `make check-links` flags `/legal-risk-disclosure` as absent from its route parser and `/favicon.svg` as missing locally; live site serves legal link and favicon successfully (HTTP 200). No unrelated route/assets changed. |
| JS advisory audit | Reported 59 findings: 1 critical, 20 high, 37 moderate, 1 low. Reachability not established. |
| Local Python installed dependency closure | 65 packages; 48 advisory records / 32 unique IDs in 7 packages. Not a hosted dependency inventory. |

The original security evidence tests assert unsafe behavior; they are not fixes.
The two oracle timestamp cases were converted into safety regressions and
additional stale/future/range/fallback tests were added. Gateway/relay tests are
separate local-only safety tests, not a financial-ledger or live integration
proof. Details in the [security review](security-review-2026-11-06.md).

Three date-dependent October tests are stabilized by pinning test-only clocks;
production expiry/freshness checks were not weakened. Repository `.venv/bin/pytest`
is absent. `make check-shared-sync` could not run for this reason; shared files
were synchronized and other shared tests passed. Whole-worktree `git diff --check`
reported a blank EOF line in the pre-existing user-modified `.gitignore`; that
unrelated file was not changed. Task-code paths passed the whitespace check.

## Still blocked — owner actions / decisions

1. Provide Render backend/matching/oracle worker logs and confirm the deployed
   contract addresses, shared JWT configuration, DB and Redis wiring. Do not
   send private keys or JWT secret values.
2. January 2027 monthly TOP20 metadata is agreed and read-only previewed. Before
   drafting/registering, complete the financial ledger and verify the admin CLI
   targets the reviewed stack (it currently uses legacy SettlementEngine).
   Do not overwrite settled legacy IDs; verify expiry, `isSettled`, fresh oracle
   and DB `onchain_index_id` together.
3. Decide the loss-gap policy. Automatic liquidation cannot guarantee a fill;
   no reserve, depositor loss or haircut is authorized by the paused decision.
4. The local oracle source now rejects old/future/invalid observations. After
   separate deployment approval, verify the hosted worker runs that code and
   reads valid timestamped data. Confirm chain price age is within both
   matching and PositionManager limits; do not extend staleness to accept old prices.
5. Provide a second normal-login test account for zero-balance, matching,
   partial-fill and account-switch browser checks. Never store credentials in repo files.
6. Deploy the reviewed service/frontend changes through the owner's normal
   process, then complete the browser matrix. Local edits do not change Vercel/Render.

## Fixes / docs / regression

- Added staged EIP-712 authorization/gateway/relay transport, explicitly not
  wired into legacy `/orders` and not a deployed financial implementation.
- Added January half-open year-window selection and Data API v2 taker-share
  volume; removed Gamma-volume substitution and block unready registration.
- Updated `api-contract.md`, `API_SURFACE.md`, both OpenAPI descriptions and
  added [V2 protocol/owner steps](relayed-execution-v2.md).
- Fresh post-change public browser check passed for Markets/chart controls and
  Explore; APIs returned 200. Portfolio showed the expected signed-out gate.
  Authenticated login and post-trade Portfolio were not verified in this run.
- No commits, pushes, redeployments, hosted migrations, or direct on-chain writes.
