# Trader-signed atomic execution V2 — staged, not activated

Status: **local components only; not end-to-end trading** (2026-11-06).
No contracts were deployed, no hosted registry rows were written, and no V2
order was submitted through the browser. `POST /orders` still uses legacy
settlement. The legacy financial vulnerabilities in the
[security review](security-review-2026-11-06.md) remain open.

## Approved requirements

- Traders authorize execution using their existing wallet, never by sending a
  private key to the matching engine. Dynamic login is unchanged.
- An operator relays one atomic matched transaction. This is not ZeroDev,
  account abstraction or a paymaster; gas sponsorship is not a release requirement.
- EOA and ERC-1271 signature verification are supported.
- Prices: 0.001 index points; sizes: 6-decimal contracts; USDC: 6 decimals.
- Per-order notional: **$10–$1,000**, leverage **1x–5x**.
- Price freshness remains required. Relaying does not justify stale prices.
- January 2027 is a **monthly** TOP20 basket, not an annual 2027 index.
- Shortfall policy is **paused**. The owner wants automatic closeout rather
  than platform-absorbed losses. Neither a funded reserve, depositor loss,
  socialized haircut nor automatic deleveraging has been approved. Liquidation
  alone cannot guarantee solvency during gaps, outages or unavailable liquidity.

## Components implemented

| File | Responsibility / limit |
|---|---|
| `contracts/src/SignedOrderExecutor.sol` | EIP-712 envelope, replay/nonce cancellation, signed size/price/notional limits, intent-preimage binding, and paired/batched atomic calls. **Not a financial ledger.** |
| `shared/xleuth_shared/trade_authorization.py` | Canonical fields, exact decimal-unit parsing, bounds, typed data and digest; vendored into the four Python services. |
| `frontend/client/lib/trade-authorization.ts` | Exact units and existing-wallet typed-data signing; verifies wallet/chain and propagates rejection. **Not connected to the trade modal.** |
| `matching-engine/src/xleuth_matching/relayed_execution.py` | One relayer-signed batch transaction, required journal interface, pending recovery and exact receipt-event validation. **No durable journal implementation or book coordinator yet.** |

These components have local safety tests in their corresponding test files.
The Solidity ledger harness and Python journal/RPC doubles are test-only and
must never be deployed as production financial implementations.

## Authorization and execution envelope

Domain: `name = Xleuth Orders`, `version = 2`, actual chain ID and deployed
executor address. The transport is restricted to Polygon Amoy (`80002`).

```text
Authorization(address trader,bytes32 basketId,bytes32 orderId,uint8 side,uint256 size,uint256 maxNotional,uint256 minPrice,uint256 maxPrice,uint256 leverage,uint256 nonce,uint256 deadline,bool fillOrKill,bool reduceOnly,bytes32 positionId)
```

- `side`: `0` buy, `1` sell. Price bounds are inclusive, positive and at most
  `100_000` milli-points. Zero final settlement is a separate, unresolved
  legacy-contract issue, not a zero-price trade supported by this gateway.
- `size`: integer micro-contracts. No integer-contract rounding or dust skipping.
- `maxNotional`: cumulative execution ceiling in micro-USDC, within
  `10_000_000`–`1_000_000_000`. Execution notional is
  `ceil(size * price / 1_000)`; each partial fill consumes that ceiling.
- The minimum is checked against the full authorized size at an execution
  price, not against each partial fill. Smaller limit-order fragments may fill.
  The ledger's actual PnL, margin, fees and rounding rules are **not implemented**.
- `orderId = keccak256(intentBytes)`. Both intent preimages are passed to the
  ledger. The gateway prevents substitution; it does not interpret order type,
  stop trigger, slippage, position generation or OCO fields. A canonical,
  versioned intent encoding and semantic validation are still required.
- `nonce` binds to one digest on first fill. A trader can cancel a nonce or
  raise their minimum nonce directly on-chain. The current browser cancellation
  endpoint does not perform this V2 cancellation. Cancellation gas/relaying is
  not implemented in the UI.
- `deadline` is valid through that timestamp. Signatures bind the domain and
  every field; ERC-1271 validity is checked on each execution.
- `reduceOnly` requires a nonzero `positionId`. Full-close, position-generation,
  OCO and reduce-only enforcement are the future ledger's responsibility.

`executeMatch(Match)` calls the ledger once with both sides.
`executeMatches(Match[])` executes all pairs in one transaction. Every FOK
authorization must be completely consumed by the end of that transaction,
including across several makers. Any invalid leg, incomplete FOK or ledger
revert rolls back all calls, fills and nonce bindings. Self-matches and
cross-basket pairs are rejected.

The constructor requires code and `executionProtocol() ==
keccak256("Xleuth Atomic Ledger v2")`. This excludes the legacy
PositionManager; **a protocol marker is not proof of a safe ledger**. Deployment
must verify reviewed bytecode, restricted write permissions and financial
invariants. A dishonest no-op ledger can claim the same marker.

Cross-language digest vector (synthetic identifiers only):
`0xdd4cdf2bedcadb6766b94138db28b3435cc8602f7cfe3efa8c97c4e1a4e877e7`.
Inputs are pinned in Solidity, Python and TypeScript tests, including a nonce
larger than JavaScript's safe integer limit.

## Transport and durable coordination requirements

The transport preflights the whole batch, signs only with the relayer account,
derives its transaction hash locally and calls `RelayJournal.record_signed`
**before** broadcast. The journal must atomically reserve a chain/relayer slot
across processes and durably retain the signed bytes plus expected fill events.
There is no in-memory production fallback. Signed transactions contain trader
authorizations; restrict access and do not log them.

Broadcast disconnects, receipt timeouts, malformed/foreign receipts and journal
failures remain `RelayPending`; they do not authorize a newly signed retry.
Restart restores a pending transaction from the journal. Reconciliation must
use the configured chain and transaction hash. Success requires status `1` and
the exact executor-emitted `MatchExecuted` digest/basket/size/price/notional
sequence for every submitted pair. A status-only success is insufficient.
Status `0` becomes `RelayReverted`, not confirmed fills.

The future coordinator must persist order/authorization/fill identities,
reserve and serialize book mutations, reconcile receipts, and apply positions
and balances exactly once. It must also implement confirmation depth/reorg
handling; the current transport proves a mined receipt, **not finality**. Neither
HTTP placement nor Portfolio currently uses this transport. Execution events
from a vetted ledger are necessary, not an independent solvency audit.

## January 2027 preparation

| Field | Value |
|---|---|
| Name | `TOP20-JANUARY` |
| Slug | `top20-2027-01` |
| Resolution window | `[2027-01-01T00:00:00Z, 2027-02-01T00:00:00Z)` |
| Expiry Unix | `1801440000` |
| New immutable index ID | `0xffc7e5da17306019916ba8e1502b59f4b195faff8655a646f1bea845356b66ea` |

The exclusive February midnight boundary labels the January period. Existing
stored names and IDs are not migrated. Explicit DB resolution windows filter
the year before volume ranking. Selection uses upstream UTC `endDate` instants,
not question text: a question about 2026 resolving on January 1 UTC is included.
Ranking still uses Gamma volume; VWAP weights use live Data API v2 cumulative
one-side **taker shares**, not USDC, with no Gamma-weight substitution.

Read-only preview command:

```bash
make basket-create THEME=TOP COUNT=20 \
  WINDOW_START=2027-01-01T00:00:00Z EXPIRY=2027-02-01T00:00:00Z DRY=1
```

The preview returned 20/20 constituents, `missing_live_volume_count: 0`,
`volume_source: data_api_v2_taker`, `volume_unit: shares`,
`ready_for_registration: true`, `warnings: []`, price **5.983**. This is a
time-specific data-readiness result, **not activation or security clearance**.
The earlier `/live-volume?id=73130` call returned 410; the documented
`/v2/live-volume?event_id=73130` returned 200.

Sources: [v2 schema](https://data-api.polymarket.com/v2/openapi.json),
[official migration guide](https://docs.polymarket.com/migrate/data-api-v1-to-v2.md).

## Activation blockers and owner steps

Do not run write/deployment commands simply because the preview is ready.

1. Decide the liquidation-gap/insolvency policy. Automatic closeout needs an
   explicit outcome when no counterparty/backing is available. Do not assume
   that liquidation at a displayed mark transfers cash or guarantees a fill.
2. Implement/review the atomic financial ledger: conserved collateral and PnL,
   paired exposure, exact cost basis/fees, margin reservations, liquidation,
   all order semantics, lifecycle/expiry, zero final outcomes and bounded
   settlement. Restrict all financial writes to authorized paths. Plan legacy
   balance/position migration; the gateway does not patch old contracts.
3. Implement the canonical intent schema, durable journal/book coordinator,
   API verification/receipt reconciliation, UI signing/cancellation and accurate
   Portfolio reads. Keep Dynamic auth intact. Do not send V2 data to legacy
   `/orders` or add trader keys as a fallback.
4. Local oracle source validation now rejects missing/old/future DB/Redis
   observations before signing. Confirm the deployed Render worker runs this
   code and that DB/Redis timestamps represent actual source observations. A
   new signature timestamp by itself is not proof of fresh input. Confirm
   configured addresses and worker logs without sharing secret values.
5. After a separately reviewed deployment/migration plan and explicit approval,
   have the owner deploy and verify the reviewed stack. Only then create the
   draft (same preview command without `DRY=1`), register using
   `make basket-register SLUG=top20-2027-01`, and read-only reconcile using
   `make basket-reconcile SLUG=top20-2027-01`. These are future **owner actions**,
   not actions performed here. The existing registrar targets the legacy
   SettlementEngine and must be checked/adapted for the reviewed stack first;
   its adoption checks do not yet establish unsettled/fresh oracle state.
6. Verify immutable ID, intended expiry, unsettled state, source and on-chain
   freshness, collateral and deployed units all agree. Then run real browser
   orders, opposite-account fills and the full
   [acceptance matrix](order-placement-verification.md#edge-case-matrix).

All source changes remain uncommitted/unpushed. No private-key operations,
hosted migrations, worker restarts or deployment actions were performed.
