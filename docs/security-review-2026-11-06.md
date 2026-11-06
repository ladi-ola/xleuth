# Security review — contracts and application, 2026-11-06

## Executive conclusion

**Not safe for real-value use; order placement target remains blocked.** This
review found locally reproducible collateral/accounting vulnerabilities and
false settlement confirmations. Subsequent staged V2 authorization/relay code,
ingestion fixes and tests are described in [the V2 protocol note](relayed-execution-v2.md).
They do not resolve the legacy financial findings or make trading safe. The
stale-oracle rejection in the live UI is a legitimate safety gate, not something
to bypass to obtain a green demo.

This is an internal, first-party, risk-directed review across the repository,
not a formal audit, a claim that every line/dependency is safe, or a complete
penetration test. No exploit was executed against hosted contracts/services.
All proof tests use synthetic local identities/keys. Some local root-cause fixes
and isolated V2 components were implemented after the initial audit snapshot;
no complete production financial remediation has been applied.

Severity describes potential financial/security impact of this architecture;
the current deployment is testnet-only with openly mintable test collateral.

## Scope and trust boundaries

| Surface | Reviewed areas | Remaining limits |
|---|---|---|
| Five first-party contracts | Custody, opening/updating/closing, PnL, liquidation, oracle signatures/freshness, expiry settlement, admin powers | No formal invariants, gas-exhaustion benchmark, or third-party audit. |
| Matching engine | HTTP auth/validation, books/FOK, margin, stop/SL/TP/OCO, idempotency, threading, bridge confirmations, registry discovery | No hosted load/chaos tests or key-using live integration tests. |
| Backend API | Auth exchange/dependencies, account ownership, faucet, DB queries, basket/portfolio reads, websocket middleware | No hosted DB/config/log access; no destructive migrations. |
| Shared code | JWT verifiers, lifecycle/ID schemas, DB transition layer, rate limiting, vendored synchronization | No live token forging; no Dynamic SDK/JWKS/auth-flow modifications. |
| Oracle / ingestion | Source timestamps, signing/push flow, discovery, selection, price/volume fallback, storage | No use of oracle/deployer keys or live push transactions. |
| Admin CLI | Registration/reconciliation, status transitions, expiry/settlement workflow | No owner transactions or registry writes. |
| Frontend | Token/cache lifetime, order conversion/mutations/errors, portfolio/deposit signing, network/websocket wiring, rendering sinks | No second-account live session test; no SDK reimplementation. |
| Infrastructure / dependencies | Compose isolation, Vite/Express/Vercel configuration, tracked env filenames/secret guard, JS/local Python advisory scans | Hosted build/dependency versions, secrets configuration and network exposure not audited. Third-party/vendor internals not exhaustively reviewed. |

Four core deployed runtimes at the **root-configured** Amoy addresses matched
local build artifacts after masking immutable references and removing metadata.
See [read-only evidence](order-placement-verification.md). That comparison does
not establish the values of all deployed immutable/configuration parameters or
prove which addresses Render currently uses.

## Critical / high findings

### C01 — Unpaired positions can withdraw profits funded by other depositors

**Critical.** `contracts/src/PositionManager.sol:207–250,323–351` permits any
caller to open/update a position for themselves, without a matched opposite
leg or signed matched-fill authorization. `CollateralVault.sol:101–109` credits
positive PnL without identifying a debited counterparty or a funded reserve.

Local proof: trader deposits 10 USDC, another account deposits 90; trader opens
a unilateral long at 50, closes at 60, and withdraws 20. Remaining vault assets
are 80 but the other depositor is still owed 90. No oracle compromise, victim
signature or matcher participation is needed; an ordinary favorable price
move is enough. `test_Evidence_UnpairedProfitCanConsumeAnotherDepositorsCollateral`.

Required direction: authenticated, bounded matched intents; atomic position and
collateral accounting; conservation/inventory invariants. Also resolve how
the documented platform-absorbed shortfall is actually funded. Merely restricting
the HTTP endpoint or adding a warning does not repair the on-chain bypass.

### C02 — Loss-free close bypasses PnL and liquidation

**Critical.** `PositionManager.sol:360–375` deletes a position and releases all
its margin without reading a price or realizing loss. A trader can choose the
profitable `updatePosition` close path for gains and this path for losses.

Local proof: 10 USDC margin, a price move from 50 to 41 leaves 1 USDC equity,
but `closePosition` restores all 10. `test_Evidence_ClosePositionDiscardsLoss`.
The older review's statement that this is a safe stale-oracle exit must not be
used as a security assurance. Exit/settlement rules need one consistent,
loss-accounting path and an explicit stale-feed policy.

### C03 — Missing settlement outcomes become confirmed fills

**Critical.** `matching-engine/.../settlement.py:258–281` drops unknown-key legs
and integer-rounded dust. `api.py:832–856` treats an absent outcome as success:
both `taker` and `maker` may be absent and a fill is still `confirmed=true`.

Local API proof: with no configured trader keys, two crossing orders return
`status=filled`, `confirmed=true`, `tx_hash=null`; the submitter is never called.
`test_evidence_missing_settlement_legs_are_confirmed_without_transactions`.
This directly violates the required "no mocked success / mined settlement"
contract. Require positively evidenced settlement for every leg; do not
silently reinterpret skipped/unknown/dust as zero-risk success.

### H01 — Gasless trader authorization is absent; settlement is custodial and non-atomic

**High.** `settlement.py:13–16,118–156,217–249` signs separate transactions with
server-held trader keys; traders pay transaction gas. Neither `OrderRequest`
nor PositionManager implements the requested relayed trader-authorization flow.
One leg may mine while the other reverts; marking both orders rejected cannot
undo the mined position. Local independent-leg proof:
`test_evidence_one_failed_leg_does_not_undo_the_other_submission`.

This is not an environment variable that can be repaired by collecting user
keys. Approve a concrete atomic authorization/relay design, replay/fill limits,
deadlines, cancellation, wallet signature support and deployment plan first.

### H02 — Collateral, price and size units disagree across layers

**High.** `margin_check.py:253–282` compares `price_int * size / leverage` as
whole USDC with a vault balance divided by 1e6. `PositionManager.sol:262,287`
locks that same product as raw token units. At price 50, size 1, leverage 5,
the engine requires 10 USDC while the contract locks **10 base units**, or
0.000010 USDC, under the current whole-index-unit bridge convention.

`frontend/.../adapters.ts:420–421` sends fractional contracts; the bridge
rounds them to integers and skips sub-half-unit positions. Portfolio/trigger
reads in `api.py:240,711,745` divide oracle values by 100 even though the
ingestion display already uses index points in the 0–100 range. A $10 order at
50 points produces 0.2 contracts, which the bridge discards. This is a financial
specification/blocker, not a display-only rounding patch. Define canonical
fixed-point units/precision and test conversions end to end before changing it.

### H03 — Expired/settled/unregistered lifecycle is not enforced on position writes

**High.** PositionManager opening/increasing checks only oracle freshness,
not SettlementEngine registration, expiry or `isSettled`. A new position can
open after the basket's one allowed settlement, leaving no normal expiry
settlement path. `test_Evidence_NewPositionCanOpenAfterBasketSettled`.

The live API labels November/December active although both legacy IDs at the
configured chain addresses are already settled. Matching refresh is not wired
to a DB pool in `main.py`/app startup, and empty/failed registry discovery can
fall back to date/name heuristics. All layers must use the same immutable ID
and authoritative lifecycle. Never reset history to make a reused ID tradable.

### H04 — Stale ingestion data can be signed with a fresh timestamp (local source validation added)

**High in the initial audit snapshot.** `oracle-service/.../price_source.py`
previously returned a scalar without validating its observation time;
`pusher.py:161–172` then signed it with the current block timestamp. A running
pusher could therefore make old DB/Redis data appear fresh indefinitely.

**Local remediation now added:** Postgres reads `scaled_price, ts`; Redis requires
`computed_at`. The composite source rejects missing/naive timestamps, stale or
future samples, and non-finite/out-of-range prices before the pusher can sign.
It falls back to another source only if that sample independently passes checks.
Regression tests now assert rejection and fresh-source fallback. This does not
prove the deployed worker runs this code or that source timestamps are
independently trustworthy. Verify deployment, clock, DB and Redis behavior.

Keep source-age/future/range/finite validation ahead of signing. **Do not merely
restart the worker and assume the new signature timestamp proves data freshness.**

### H05 — Stop evaluation mutates its dictionary during iteration

**High.** `orderbook.py:331–365` pops from `_stop_orders` while iterating it.
The first trigger raises `RuntimeError: dictionary changed size during iteration`.
The outer evaluator catches/logs it, but results/fills may already have mutated
before settlement or book publication. Local deterministic proof:
`test_evidence_triggering_a_stop_mutates_the_iterated_dictionary`.

Use a safe execution plan/snapshot with transactional state transitions,
and ensure execution failures cannot consume liquidity without settlement.

### H06 — SL/TP is not safely bound to the current position/OCO lifecycle

**High.** `_get_position_from_chain` ignores `position_id`; an arbitrary ID
is accepted if any position exists on that basket (local proof included).
Side/size are captured at placement and not re-derived at trigger, so a prior
close/reversal/partial change can turn supposed full-close protection into
an entry or an over-close. Trigger loops skip margin/lifecycle/freshness checks.

OCO groups are keyed by caller-supplied strings without a wallet/position
namespace. `check_sltp_triggers` snapshots sibling entries before cancellation
and does not check that each snapshot item is still pending before execution.
Sibling removal occurs before chain success. Test/update exact-one-close,
stale position generations, group isolation, failed execution and cancel races.

### H07 — Resting margin is not reserved; fill/trigger risk is not rechecked

**High.** Margin validation reads free vault collateral for each incoming order
independently. No reservation ledger is applied. Local proof accepts two
resting orders each requiring the full same 1,000 USDC. Makers and triggered
orders can later have insufficient collateral or changed exposure. Opposite
orders are also charged opening margin even when reducing an existing position.

Implement consistent reservations and execution-time validation together with
atomic settlement; a UI balance check cannot make the underlying book solvent.

### H08 — Idempotency and book state are not concurrency-safe or durable

**High.** Synchronous FastAPI routes execute in worker threads, contrary to
`api.py:28–29`'s "naturally serialized" claim. Checking an idempotency key and
remembering it after placement is non-atomic. A barrier-controlled local proof
submits the same wallet/key concurrently and gets **two different order IDs**.

Books, history, protective orders, reservations and idempotency are memory-only
and disappear on restart/cold-start. Replayed keys are not bound to a payload;
rejected paths are inconsistently recorded. Define durable order-intent/state
transitions and serialize shared mutation/nonce use. Do not disable duplicate
protection or silently re-post after an ambiguous timeout.

### H09 — Cached credentials and account data outlive SDK logout/account changes

**High.** `frontend/.../token-exchange.ts:27–40` returns an internal cached token
before checking the current SDK identity. Logout handlers never clear it;
authenticated Query keys are not wallet-scoped and caches are not cleared on
identity change. Local tests return user A's internal token after SDK logout
and after switching the mocked SDK identity to B.

Fix the application's internal-token/query lifecycle without rewriting Dynamic
login. Cancel stale identity-bound refreshes and test logout/login/account
switch during in-flight requests. Second-account browser verification pending.

### H10 — Production can start with the public example JWT signing secret

**High, configuration-dependent.** Backend `main.py:131` and matching
`config.py:101` fall back to the same known example secret; shared configuration
only warns. Internal verification does not require an expiration claim or an
EVM-shaped subject. A local token signed with that example secret and no `exp`
is accepted (proof test included).

This does **not** prove Render uses a weak secret, and no forged token was sent
to a hosted API. Fail closed on absent/example secrets at startup; require
typed/required claims and test valid/expired tokens without weakening auth.
Rotate deployed secrets only if owner configuration/history shows exposure.

## Additional material findings

| ID | Severity | Source, impact and required direction |
|---|---|---|
| M01 | Medium | `PositionManager.sol:294`: integer weighted entry truncation destroys real PnL. Local two-leg example loses a 0.1 USDC loss after entry 50/51 is rounded to 50. Track exact cost basis or bounded fixed-point rounding; test both sides and dust cycles. |
| M02 | Medium | `IndexOracleConsumer.sol:84–85`, `SettlementEngine.sol:119`: no upper timestamp bound. Valid future-signed data passes age checks; oracle monotonicity can block genuine updates and PositionManager treats it as fresh. Local oracle proof passes one day later with a year-future timestamp. Requires authorized signer error/compromise, not arbitrary forgery. |
| M03 | High availability | `SettlementEngine.sol:118`, `PositionManager.sol:438` reject zero realized settlement, although all-NO is a valid 0–1 basket result. Local valid zero-settlement message reverts. Support zero final outcome with explicit validity state; do not equate zero with missing data. |
| M04 | Medium/high scaling | `PositionManager.sol:440–463`: all-user settlement is an unbounded loop in one transaction. Opening many tiny positions can make expiry settlement exceed the gas limit. No live DoS attempted; batching/claims and bounds require a reviewed design. |
| M05 | Medium | `faucet.py:95–106,136,179–205`, `db.py:427–448`: cooldown is check-then-write, operator nonce reads are unsynchronized, DB outage removes persistence, and a reverted receipt still returns `submitted`; UI always says claim successful. Concurrent claims/nonce collisions and false funding claims possible. Use atomic reservations, pending/reverted reconciliation and fail-closed persistence. No live concurrent claims made. |
| M06 | Medium | `api.py:741–749` uses `keccak(NAME)` for a second position read even with a DB ID, then fabricates entry/margin fallbacks. `accounts.py:127–145` hardcodes used margin/PnL zero and omits locked collateral from total balance. Return accurate chain/ledger data or an explicit unavailable state, never guessed success. |
| M07 | Medium | `RateLimitMiddleware` trusts only `Content-Length`, not consumed body bytes; chunked bodies can evade its own limit. Per-IP hit keys are unbounded, HTTP GET/RPC-heavy reads and websocket connections are not limited. `TRUST_PROXY=1` trusts the leftmost forwarded value without a trusted-proxy list. Upstream limits were not verified. |
| M08 | Medium | Websocket handlers create per-connection queues/pubsubs without guaranteed unsubscribe/close cleanup and accept arbitrary basket channels. Frontend factories use a mismatched ping/subscribe shape; `Markets` uses HTTP queries but never mounts these clients and public queries do not poll. Snapshot type/shape also differs. Reconnect helpers existing in source do not prove live state refresh. |
| M09 | Medium | `ApiError.fromUnknown` converts absent network status to 500, making the hooks' `if (!apiError.status)` ambiguity handling unreachable (local proof). All 429s are called faucet cooldown, including order rate limits; `price_out_of_range` is absent from the typed rejection mapping; HTTP-201 `status=rejected` is not treated as a mutation error. Audit every rejection and preserve unknown status/reconciliation. |
| M10 | Medium | Numeric boundaries are incomplete: float `size`/`price` allow non-finite values in some paths, no maximum size/notional or canonical precision is enforced, trigger bounds/ticks differ, and huge integer conversions/rounding can break serialization/settlement. Owner must specify limits; enforce finite, bounded, fixed-point values consistently. |
| M11 | Medium | `basket_builder._fetch_all_markets` silently publishes partial discovery after a paging error; `_resolve_price` can substitute the other outcome's token if YES is missing. Selection ignores the year/window and configured liquidity rules; fallback Gamma volume/price can change index quality. `realized_fraction` treats malformed/unresolved outcomes as NO. Require explicit data-quality/resolution rules; do not silently invent a market outcome. |
| M12 | Medium ops | `admin-cli/cli.py:221–237` can mark a basket DB-settled while on-chain settlement is a TODO. Registration adoption does not check `isSettled` or fresh oracle, and reconciliation never reads `isSettled` despite the ABI containing it. Disallow status success without matching chain evidence. No admin operation performed. |
| M13 | Medium ops | `oracle-service/price_source.py:79` and ingestion `redis_publisher.py:27` log raw Redis URLs, which may contain credentials; config dataclass repr includes key fields. No real leaked URL/key is reproduced in this report. Redact credentials at logging/config boundaries; owner should inspect/redact historical logs and rotate only if exposure occurred. |
| M14 | Medium hardening | Browser same-origin HEAD 200 on the live frontend returned no CSP, HSTS, X-Frame-Options, nosniff, referrer or permissions policy headers. `vercel.json` sets no headers. Review wallet/widget-compatible CSP and anti-framing policy in report-only/testing before enforcing; do not break Dynamic/charts with guessed allowlists. |
| M15 | Medium, deployment-dependent | Compose publishes Postgres/Redis to all interfaces, Redis has no configured auth, DB has a default password, and every Python service receives the whole root `.env` including unrelated key material. Bind local ports/segment privileges and give each service only required secrets. Actual hosted firewall/secret setup not inspected. |
| M16 | Low/operational | API Redis startup uses host/port rather than authenticated/TLS `REDIS_URL`; matching DB registry pool/refresh bootstrap is absent. Runtime may degrade silently despite Render URLs being configured. Verify deployment wiring and surface health/readiness. |

## Dependency advisory findings

`corepack pnpm audit --json` reported **59 occurrences** (1 critical, 20 high,
37 moderate, 1 low). Examples include `proxy-addr` (critical,
GHSA-jqcg-44mw-7w3h), React Router, axios, bigint-buffer, Vite, Vitest,
body-parser, and zod. Advisory severity is **not** application exploitability:
Express is a development stub, this is not an SSR deployment, and some findings
require Node-only adapters or exposed development servers. Triage dependency
paths/build output and minimally upgrade with login/chart regressions; do not
perform a blanket Dynamic/React major migration.

`pip-audit` scanned the local installed dependency closure (65 packages), not
the Render environment: **48 records / 32 unique advisory IDs** across PyJWT,
cryptography, requests, urllib3, idna, certifi and pygments. Some feed records
are duplicated. The local versions are PyJWT 2.10.1, cryptography 46.0.5,
requests 2.32.5, urllib3 2.6.3, idna 3.11, certifi 2026.1.4, pygments 2.19.2.
The raw audit output and pinned inventory are outside the repository under
`/tmp/opencode/xleuth-order-qa/`. Python requirements mostly use open lower
bounds and backend pins FastAPI 0.115.0, so current local tests do not establish
the versions or security posture of deployed dependency resolution. Obtain
hosted lock/build inventories and audit them before a release.

Tracked env-file inventory contained `.env.example` files, not root real `.env`;
the existing `make check-secrets` placeholder guard passed. This is not proof
that no secret exists anywhere in git history or deployment logs.

## Evidence tests added

| File | Proofs | Result |
|---|---:|---|
| `contracts/test/SecurityReview.t.sol` | 6 | Local exploit/unsafe behavior reproduced. |
| `matching-engine/tests/test_security_review.py` | 6 | Local API/book/bridge failures reproduced. |
| `frontend/client/lib/api/security-review.spec.ts` | 3 | Credential cache/network classification failures reproduced. |
| `oracle-service/tests/test_security_price_freshness.py` | 2 | Old DB/Redis samples accepted. |
| `shared/tests/test_security_internal_jwt.py` | 1 | Example-secret/non-expiring synthetic token accepted locally. |

The original local evidence tests assert unsafe behavior; they are not
successful fixes. The two oracle freshness tests have since been converted to
safety regressions, with additional timestamp/range/fallback coverage. Replace
remaining assertions with their desired security properties when each issue is
remediated (rejection, conservation, atomicity, exact units or identity binding).
The baseline contract suite's 92 passes missed these cases; the expanded
contract suite now has 129 passes, including 31 isolated gateway tests. Matching
has 113 passes, including V2 transport tests. These do not prove legacy financial
safety. Details are in [the verification report](order-placement-verification.md).

## Recommended remediation sequence — requires owner decisions

1. Do not enable real-value trading or restart pushes just to defeat stale-price
   rejection. Preserve historical basket settlement state and logs.
2. Authorization/signature support and precision limits are approved and staged;
   complete canonical order intents and decide liquidation-gap/shortfall policy
   before implementing or enabling the financial ledger.
3. Implement and test atomic matched authorization/settlement, position lifecycle,
   loss-accounting and conservation; explicitly plan existing-state migration.
4. Repair book/reservation/idempotency durability, protective order evaluation,
   source freshness and correct lifecycle/ID discovery at the actual roots.
5. Repair application identity cache, status/error truthfulness, portfolio and
   streaming correctness, rate/secret boundaries and dependency findings.
6. Replace vulnerability evidence assertions with safety regressions, add
   financial/state-machine invariants, and complete browser acceptance on a
   fresh registered basket after separate deployment/owner action approvals.

Open decisions and exact owner actions are tracked in
[the checkable spec](order-placement-spec.md), [V2 execution note](relayed-execution-v2.md),
and verification report. No
contract migration, changed margin/settlement policy, private-key use or
deployment has been assumed authorized by this review.
