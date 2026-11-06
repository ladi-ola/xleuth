# Order placement: checkable execution spec

Derived from `../PLAN.md` and `../AGENTS.md`; extended by the owner's request
for contract and codebase security review. Status: **blocked, not complete**
(2026-11-06). An unchecked item is not an implemented or verified feature.

## Constraints and permissions

- [x] Read root instructions, `architecture.md`, README, PLAN, and frontend instructions.
- [x] Target confirmed: https://www.xleuth.xyz.
- [x] Hosted API URLs confirmed from actual browser requests.
- [x] Owner permitted faucet claims and test orders that may settle on Amoy.
- [x] Owner permitted contract source changes if necessary.
- [ ] Separate owner approval for a specific deployment, registry write, or migration.
- Preserve Dynamic login, existing screens/layout, charts, disabled Withdraw,
  order semantics, 1–5x UI leverage, and formatting helpers.
- No trader-key collection, auth bypasses, mocked successes, commits, or pushes.
- Existing changes in `.gitignore`, `frontend/.env.example`, and the OpenZeppelin
  submodule belong to the owner and must remain untouched.

## Sequential acceptance gates

### S01 — Reproduce before changing production code

- [x] Use `agent-browser` to sign in through normal Dynamic email/code login.
- [x] Open a basket and submit a basic limit buy through the existing modal.
- [x] Capture actual order payload, HTTP status/body, visible state, and console errors.
- [ ] Correlate hosted backend/matching logs (owner access/logs required).
- [x] Identify the first failing layer: matching margin gate, `oracle_price_stale`.

Evidence and limitations: [verification report](order-placement-verification.md).

### S02 — Establish valid trading preconditions

- [x] Confirm the signed-in account has vault collateral: 1,000 test USDC.
- [x] Confirm Dynamic exchange and matching authenticated reads return 200.
- [x] Confirm both services and browser CORS requests are reachable after startup.
- [x] Confirm ingestion snapshots are current; do not assume ingestion is absent.
- [x] Read actual oracle/lifecycle state without signing transactions.
- [ ] Restore a genuinely fresh on-chain oracle from fresh ingestion data.
- [ ] Select/register an owner-approved, unique, unsettled basket with correct expiry.
- [ ] Reconcile DB/API basket IDs, lifecycle, and chain state.
- [ ] Verify successful faucet-to-tradeable-collateral flow for a zero-balance account.

Both UI-active legacy basket IDs are already settled on the configured chain.
Do not reset history or re-register those IDs to disguise that state.

### S03 — Resolve architecture decisions before implementing

- [x] Owner approved trader-signed authorization and atomic relaying, without
  gas sponsorship or account abstraction. Gateway/transport prototypes exist;
  they are not wired into the legacy endpoint and no financial ledger exists.
- [x] Support EOA and ERC-1271 wallets; do not change Dynamic login or add AA.
- [x] Owner approved 0.001-point prices, 6-decimal contracts/USDC, and
  $10–$1,000 notional limits. Helpers/gateway implement the authorization
  envelope, but end-to-end financial accounting conversions remain unproven.
- [x] Price freshness stays required; do not sign old source data as fresh.
- [x] January 2027 monthly TOP20 window/metadata selected; read-only preview
  passed. No DB draft or on-chain registration has been created.
- [x] Owner selected full maximum-loss collateralization; leverage is only a
  position-size ceiling and execution must reject unless worst-case loss is
  escrowed. This is not implemented. Automatic closeout cannot guarantee fills;
  ledger tests must prove gap/expiry/PnL conservation without platform backing.
- [ ] Obtain an owner plan for registration/deployment and any existing balances.

### S04 — Fix demonstrated root causes with tests

- [x] Stage signed envelope, replay protection, fill/notional limits, deadlines,
  nonce cancellation and EOA/ERC-1271 checks in isolated V2 components.
- [x] Stage atomic paired/multi-maker transport and receipt-event checks; it is
  not wired to orders and has no production journal or financial ledger.
- [ ] Require atomic writes in the live application; legacy false confirmations
  and one-sided settlement remain demonstrated critical issues.
- [ ] Preserve collateral conservation; remove loss-free unilateral closes and
  prevent unbacked profit withdrawals.
- [x] Add shared, browser and Solidity fixed-point authorization helpers/tests.
- [ ] Apply exact units to live matcher, ledger, portfolio, fees and PnL; legacy
  rounding and accounting remain unsafe.
- [ ] Enforce registered, active, unexpired, unsettled baskets at execution.
- [ ] Reserve resting-order margin, revalidate at trigger/fill, and release it
  on cancellation/rejection; reducing exposure must not require opening margin.
- [ ] Make idempotency and state mutation concurrency-safe and durable across restarts.
- [ ] Make stop/SL/TP evaluation safe, position-bound, full-close-only and OCO-correct.
- [ ] Show accurate order/position/balance/margin/PnL state without fake fallbacks.
- [ ] Correct rejection, network ambiguity and timeout handling in existing UI.
- [ ] Add safety regression tests for each fix; convert relevant security proof
  assertions from observed vulnerability to desired rejection/conservation.

### S05 — Browser edge-case sweep (after S02–S04)

- [ ] Limit buy and limit sell.
- [ ] Market buy and market sell (FOK, bounded slippage).
- [ ] Stop buy and stop sell (mark-triggered market conversion).
- [ ] SL/TP attach, edit, cancel, OCO and position-size/side changes before trigger.
- [ ] Every leverage 1–5x; max leverage with exact and just-short collateral.
- [ ] Size/price: zero, negative, below min, above max, excessive decimals,
  tiny/huge, non-finite, and out-of-range prices.
- [ ] Insufficient margin and unfunded/no-faucet account.
- [ ] Slippage hit, insufficient-liquidity FOK, and empty book.
- [ ] Resting, partial fill, full fill, cancellation, and repeated cancel.
- [ ] Self-trade/crossing and multiple orders at one price/time priority.
- [ ] Expired, resolved, upcoming, unregistered and stale-oracle baskets.
- [ ] Signed out, invalid/expired session, account switch, and refresh mid-submit.
- [ ] Double submit, slow/failed network, cold start, timeout and reconciliation.
- [ ] Websocket disconnect/reconnect and subsequent state consistency.
- [ ] Portfolio orders/positions/summary, balances, margin and 3-decimal prices/deltas.
- [ ] All backend rejection codes have specific human-readable UI messages.

Every case must have PASS / FAIL / NOT-TESTABLE and evidence in the verification
report. Local proofs and unit tests do not substitute for browser acceptance.

### S06 — Security review and release gate

- [x] Perform initial first-party, full-surface security review and prioritize findings.
- [x] Reproduce representative vulnerabilities locally with synthetic credentials.
- [x] Run JavaScript dependency advisory scan and local Python dependency scan.
- [ ] Remediate findings and independently re-test safety properties.
- [ ] Confirm actual hosted dependency versions and deployment configuration/logs.
- [ ] Review upgrade/migration consequences, operational keys and signer rotation.
- [ ] Applicable suites green; isolate/fix baseline date-dependent test failures.
- [ ] Browser regression: login, chart, Explore and Portfolio after actual fixes.
- [ ] If API behavior changes, update `api-contract.md`, `API_SURFACE.md` and both OpenAPI JSONs.
- [ ] Complete final root-cause/file-by-file report with order IDs and mined hashes.

Security findings: [2026-11-06 review](security-review-2026-11-06.md).
Staged V2 protocol and January preview:
[V2 execution status](relayed-execution-v2.md).
