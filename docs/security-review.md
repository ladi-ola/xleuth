# Security Self-Review — Smart Contracts (Week 6)

> **Historical review — superseded for release decisions.** The
> [2026-11-06 contracts and application review](security-review-2026-11-06.md)
> reproduces critical collateral and settlement vulnerabilities missed below.
> Its passing evidence tests demonstrate vulnerabilities, not fixes. Do not
> interpret the older verdicts as current security assurance.

Scope: the five contracts in `contracts/src/` deployed on Polygon Amoy
testnet (CHAIN_ID 80002):

| Contract | Address | Role |
|---|---|---|
| CollateralVault | `0x6dbeEb6a5bE0cD63159b1dBD5525dE125A1CECef` | custody of all user collateral (test-USDC) |
| PositionManager | `0x65e2687284c64576d2B7Cd55393163Fb9f6871ef` | open/increase/flatten/close/settle/liquidate positions |
| IndexOracleConsumer | `0xd394B8A5dace5EB22933A2a0DCE1C82c1Eb70cd2` | verifies signed index-price updates |
| SettlementEngine | `0x68aa3697b1783cb671c575D01C5622c2FA8570e8` | enforces expiry + settle-once, settles baskets |
| MockUSDC | `0xc8783E02f3EE944BdE2990DbcDFefbe8adc3e86D` | testnet-only collateral token (open mint) |

All contracts compile with `pragma solidity ^0.8.24` — **checked arithmetic is
on by default** everywhere (no `unchecked` blocks, no custom assembly, no
`delegatecall`). Only trusted, known contracts are called (vault, oracle,
position manager, settlement engine, USDC). Foundry suite: **92 tests pass**
(38 PositionManager, plus vault/oracle/engine suites), and the Week-6 live E2E
exercised open → increase → flatten → settle on Amoy with real funds.

---

## 1. Reentrancy

| Contract | Verdict | Why |
|---|---|---|
| CollateralVault | ✅ protected | `nonReentrant` on every state-changing function (`deposit`, `withdraw`, `lockMargin`, `releaseMargin`, `settlePosition`, `liquidatePosition`). All state is updated **before** the only external calls (`safeTransfer` / `safeTransferFrom` of USDC — a trusted, non-reentrant ERC20). |
| PositionManager | ✅ no surface | Calls only the vault and oracle (trusted siblings). Neither calls back into the PM. No token transfers happen in the PM itself. |
| IndexOracleConsumer | ✅ no surface | `pushPrice` is a single-state-write function; no external calls. |
| SettlementEngine | ✅ no surface | Calls only `PositionManager.settleBasket`; no token flows, no callbacks. |
| MockUSDC | ✅ no surface | OpenZeppelin ERC20. |

No untrusted-contract interaction exists anywhere in the position lifecycle,
so there is no callback vector to reenter with.

## 2. Integer over/underflow on fixed-point math

- Solidty 0.8.24 checked arithmetic on all `uint256`/`int256` math; no
  `unchecked` blocks.
- PnL is computed as `int256(price) - int256(entryPrice)` then `* size` —
  with prices bounded to `[0, 100]` by the oracle and `size` bounded by
  margin affordability, no overflow is reachable; casting is always guarded
  by range checks before `int256 -> uint256` conversions.
- Margin = `price * size / leverage`, and `margin == 0` **reverts**
  (`InvalidPrice`) — a zero-margin position can never be created, even at
  index prices of 1 (verified live: entry=1, margin=4).
- Losses are floored at zero in the vault (`credited = total > 0 ? total : 0`);
  balances are never pushed negative, and the residual shortfall is absorbed
  by the platform — an explicit, documented design decision (not a bug).
- Equity math in liquidation (`equity = locked + pnl`, clamped) cannot
  underflow: `uint256(equityPos)` is only taken when `equity > 0`.

## 3. Access control — every state-changing function

**CollateralVault**
- `deposit` / `withdraw` — any user, acting on themselves only. ✅
- `lockMargin` / `releaseMargin` / `settlePosition` / `liquidatePosition` —
  `msg.sender == positionManager` only; a wrong caller reverts
  (`NotPositionManager`). ✅
- `setPositionManager` — `onlyOwner`, zero-address guarded. ✅
- Locked margin can never be withdrawn directly (withdraw reads only
  `freeBalance`). ✅

**PositionManager**
- `openPosition` / `updatePosition` / `closePosition` — any user, own
  positions only; `closePosition` reverts on no open position. ✅
- `settleBasket` — `msg.sender == settlementEngine` only. ✅
- `liquidate` — **permissionless by design** (anyone can trigger for the
  liquidator reward); safe because it is restricted to positions below the
  maintenance threshold and the reward is clamped to the position's equity
  inside the vault (no insolvency path). ✅
- `setMaxLeverage`, `setMaxStaleness`, `setMaintenanceMarginRatio`,
  `setLiquidationFee`, `setSettlementEngine` — `onlyOwner`, zero/zero-value
  guarded. ✅

**IndexOracleConsumer**
- `pushPrice` — permissionless **by design**: the EIP-712 signature is
  verified against `authorizedOracle` before any state change, so
  unauthenticated callers can only relay messages signed by the authorized
  oracle. ✅
- `setAuthorizedOracle`, `setMaxStaleness` — `onlyOwner`, zero-address
  guarded. ✅

**SettlementEngine**
- `settleBasket` — permissionless relay of a signed message; signer must be
  `authorizedSigner`, timestamp within `maxSettlementStaleness`. ✅
- `setBasketExpiry`, `setAuthorizedSigner`, `setMaxSettlementStaleness` —
  `onlyOwner`. ✅

## 4. Oracle staleness handling

- `IndexOracleConsumer.pushPrice` rejects: out-of-order updates
  (`timestamp <= last.timestamp`), stale updates
  (`timestamp + maxStaleness < block.timestamp`), out-of-range prices
  (`price == 0 || price > priceScale`), and unauthorized signatures. ✅
- `PositionManager._requireFreshPrice` gates **every** price-dependent path —
  open, updatePosition (open/increase/flatten), liquidate — reverting
  `PriceNotFresh` when the price is older than `maxStaleness` or zero.
  Verified by tests and live: `oracle_price_stale` also blocks order
  placement at the engine layer. ✅
- `closePosition` intentionally does not read the oracle (it only releases
  margin), so a stale feed cannot lock users out of closing. ✅
- EIP-712 domains are distinct between the oracle
  (`"Xleuth Index Oracle"/1`) and settlement (`"Xleuth Settlement"/1`), so a
  signature from one domain cannot be replayed against the other. ✅

## 5. Settlement integrity

- Settle-once enforced (`isSettled`), set **before** `positionManager.settleBasket`;
  any revert rolls back the whole transaction (atomic). ✅
- `NotExpired` (`block.timestamp >= expiry`) enforced in the engine. ✅
- Per-position payouts: `creditedBack = locked + pnl` when solvent,
  floored at zero when wiped; every open position is settled and removed
  from `openUsers`. ✅

## Findings worth hardening (none exploited, none high-severity in the testnet scope)

| # | Finding | Severity | Note / mitigation |
|---|---|---|---|
| 1 | `PositionManager.settleBasket` does **not** itself re-check expiry or settled state — it trusts `settlementEngine` for both. | Medium (testnet) | A misconfigured/malicious engine address (owner-controlled) could settle a basket at an arbitrary value before expiry. Owner is the trust root pre-audit; hardening: mirror expiry + settled checks in the PM. |
| 2 | `SettlementEngine.settleBasket` iterates **all** open users in one transaction — unbounded gas loop. | Medium (scaling) | With many open positions the tx could hit the block gas limit and settlement would fail (no worse: it reverts atomically, nothing half-settles). Hardening: batched/claim-based settlement. |
| 3 | Single authorized oracle signer + single settlement signer (centralized). | Accepted descope | MVP design; key rotation exists (`setAuthorizedOracle`, `setAuthorizedSigner`); decentralization is an explicit descope (see deployment-status.md). |
| 4 | Oracle accepts future timestamps (no upper bound), so a compromised signer could pre-push timestamps to block later updates. | Low | Signer is trusted ops; pusher only uses block timestamps. Hardening: bound `timestamp <= block.timestamp`. |
| 5 | `setLiquidationFee` has no cap (owner could set 100% of notional as the fee). | Low | Reward is clamped to position equity in the vault — no funds beyond the position can move; owner trusted. |
| 6 | `CollateralVault.totalCollateral()` = token `balanceOf(vault)` can drift from internal accounting if tokens are transferred directly to the vault (dust). | Informational | Cosmetic; internal free/locked accounting is authoritative. |
| 7 | `FeeExceedsNotional` error declared in PositionManager but never used. | Informational | Dead code; remove in a cleanup pass. |
| 8 | No trading fees, no pause/emergency-stop, no owner-multisig/timelock. | Accepted descope | Documented in deployment-status.md. |

## What was explicitly NOT covered pre-audit (honest list)

- **No third-party audit** — this review is internal, code-level.
- **No formal static-analysis or fuzzing harness** (Slither/Aderyn/Echidna not
  yet run); coverage is Foundry unit + integration tests plus the live Amoy E2E.
- **No invariant/property tests** yet (e.g. "sum of margins never exceeds vault
  balance", "no user balance ever goes negative" as fuzz targets).
- **No MEV / ordering (front-running) analysis** — e.g. liquidations and
  oracle pushes are front-runnable in principle; impact is bounded by the
  clamped reward and trusted signer.
- **No gas-DoS mitigation** for settlement with many users (finding #2).
- **No oracle decentralization**, no mainnet-grade collateral (MockUSDC open
  mint), no multisig/timelock on owner keys, no fee model, no insurance
  pool, no circuit breakers.
- Testnet tokens only — none of this has real-money risk today; a mainnet
  launch would require a full external audit before anything else.
