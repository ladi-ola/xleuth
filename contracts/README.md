# Xleuth Contracts (Weeks 3–4)

Foundry project for the Xleuth cash-settled dated index futures platform on
Polygon Amoy testnet.

## Contracts

| Contract              | Purpose                                                                                    |
|-----------------------|--------------------------------------------------------------------------------------------|
| `CollateralVault`     | Custody of test-USDC; per-user free vs. locked (margin) balances; OZ `SafeERC20` + `ReentrancyGuard`. Only the PositionManager may lock/release margin. Week 4 adds `settlePosition` (floor-at-zero write-off settlement) and `liquidatePosition` (liquidator fee capped at position equity, remainder to user). |
| `PositionManager`     | Opens/closes long/short positions per user per basket_id. Margin = notional / leverage, read from the IndexOracleConsumer (must be fresh). Leverage cap is owner-settable. Week 4 adds per-basket open-user enumeration, `liquidate` (any caller, maintenance-margin ratio in bps, strict-below boundary), and `settleBasket` (SettlementEngine-only, loops all open users). |
| `SettlementEngine`    | Week 4: expiry registry per basket; accepts an EIP-712 signed realized YES fraction (`SettleBasket(bytes32,uint256,uint256)`), rejects pre-expiry/unknown/already-settled/stale/unauthorized messages, and settles every open position via `PositionManager.settleBasket`. Any caller may relay a valid signature. |
| `IndexOracleConsumer` | Single authorized EIP-712 signer pushes `(basketId, price, timestamp)` updates; rejects unauthorized and stale updates. Prices scaled 0–100. Fed by the Python `oracle-service` (Week 4). |
| `MockUSDC`            | Testnet-only 6-decimal USDC stand-in with an open mint. Never mainnet.                     |

## Design decisions (locked)

- Margin = `(size × oracle price) / leverage`, price read live from the oracle consumer.
- Liquidation ratio (bps) = `equity × 1e4 / notional`, liquidatable strictly below the
  configurable `maintenanceMarginRatioBps`; boundary (`==`) is NOT liquidatable.
- Liquidator reward = `liquidationFeeBps` of notional, capped at position equity; remainder
  returned to the user. A fully wiped position pays no reward.
- Settlement: realized value is the volume-weighted YES fraction of the basket
  (0–priceScale), signed EIP-712 by a designated signer; any relayer may settle
  post-expiry. Losses floor at zero — residual shortfall is absorbed by the platform.
- Trades require a fresh oracle price (within `maxStaleness`); stale prices revert.
- One net position per user per basket_id; opening opposite side on an existing position reverts.
- EIP-712 oracle signature: `PriceUpdate(bytes32 basketId,uint256 price,uint256 timestamp)`, domain "Xleuth Index Oracle" v1.
- EIP-712 settlement signature: `SettleBasket(bytes32 basketId,uint256 realizedPrice,uint256 timestamp)`, domain "Xleuth Settlement" v1.

## Usage

```bash
forge build
forge test --gas-report          # full suite incl. fuzz + gas tables
forge fmt --check

# Deploy (reads contracts/.env — gitignored, never commit real keys)
make deploy-testnet              # or: forge script script/DeployAmoy.s.sol:DeployAmoy --rpc-url $RPC_URL --broadcast

# Seed initial signed prices for ACTIVE_BASKETS
make deploy-config-baskets       # or: forge script script/ConfigureBaskets.s.sol:ConfigureBaskets --rpc-url $RPC_URL --broadcast

# Register expiry + settle a basket at a realized fraction
make deploy-settle-basket        # or: forge script script/SettleBasket.s.sol:SettleBasket --rpc-url $RPC_URL --broadcast
```

New env vars for Week 4 (contracts/.env): `SETTLEMENT_ENGINE_ADDRESS`,
`SETTLEMENT_SIGNER_PRIVATE_KEY`, `MAINTENANCE_MARGIN_RATIO_BPS=625`,
`LIQUIDATION_FEE_BPS=50`, `SETTLEMENT_MAX_STALENESS_SECONDS=3600`,
`BASKET_EXPIRY_SECONDS=0`.

## Safety status and isolated V2 ledger

**Do not redeploy the legacy stack or use it for new trades.** The existing
`PositionManager`/`CollateralVault` permit unilateral position updates,
unfunded PnL credits and loss-free `closePosition` exits. The old
legacy deployment and basket-registration scripts are disabled. Existing Amoy addresses and balances remain
untouched; no migration is performed by this repository change.

`AtomicTradeLedger.sol` is a separate, fully reserved matched-lot ledger for
`SignedOrderExecutor`: both parties' worst-case losses are locked in its own
custody before a lot opens, and settlement redistributes exactly those
reserves at a signed final price (including zero). Settlement runs in bounded
permissionless batches. The ledger is deployed first, then the executor, then
`bindExecutor` locks the executor address once. The selected 1–5x leverage is
recorded in the authorization, but collateral requirements use the **full
worst-case loss**, not `notional / leverage`.

**Not ready for live cutover:** the new ledger checks canonical, versioned
opening intents (limit/market/breakout stop) and matched lot-bound reductions.
SL/TP closes require the full lot and a signed trigger and OCO group; the first
matched close transfers ownership, invalidating the other leg. Partial ordinary
closes split a lot. A match where *both* traders try to close existing lots is
rejected; the off-chain book must surface that case clearly. The backend
still has a legacy per-trader settlement bridge; do not enable it for this
ledger. Before deployment, the owner must arrange independent review, run the
Foundry suite, integrate a durable atomic relay/receipt journal and compatible
frontend deposit and order signing, and plan migration for legacy balances.
Do not point the new ledger at the old vault or flip environment addresses as
a shortcut. No contracts have been deployed by these changes.

Opening intent preimage (160 bytes):
`abi.encode(uint8 kind, uint256 triggerPrice, bytes32 ocoGroup, bytes32 positionId, bytes32 salt)`;
`orderId = keccak256(preimage)`. Kind 0=limit, 1=market, 2=breakout stop;
3=stop-loss, 4=take-profit. Market/stop and SL/TP require a signed fill-or-kill
flag. For opening trades the group and position ID are zero and salt is unique
and nonzero. For a reduce-only close, `positionId = bytes32(lotIndex + 1)`
within the signed basket; SL/TP require a nonzero OCO group. The shared Python
and frontend TypeScript helpers use this exact encoding. The new deployment
script requires an explicit `ATOMIC_CUTOVER_APPROVED=1` gate and must not be
broadcast before settlement, close, funding and portfolio integration and
separate owner confirmation.

## Amoy deployments (2026-08-03 — RedeployCore)

| Contract            | Address                                                                                                            |
|---------------------|--------------------------------------------------------------------------------------------------------------------|
| CollateralVault     | `0xfED3B63efEF00fDff499c1dC86cac45b99CE0579` (Week-4 code: `settlePosition`, `liquidatePosition`) |
| PositionManager     | `0x438E9DFDaf2f0a24ef135fD7b7f8B128AFfF33e4` (Week-4 code: `liquidate`, `settleBasket`, `setSettlementEngine`) |
| IndexOracleConsumer | `0xd394B8A5dace5EB22933A2a0DCE1C82c1Eb70cd2` (reused; deployer key is the authorized signer) |
| MockUSDC (test-USDC)| `0xc8783E02f3EE944BdE2990DbcDFefbe8adc3e86D` |

Week-3 contracts (`0xdd12...` vault, `0xAbDa...` PM) are superseded: the vault and
PM are immutable-bound, and the old vault was deployed before the Week-4
settle/liquidate functions existed — a mid-life upgrade is impossible without a
full redeploy. A `SettlementEngine` is NOT deployed on-chain yet (local tests
only); to add it: deploy via `RedeployCore` with `REGISTER_ENGINE=1` or a
dedicated engine script, then set `SETTLEMENT_ENGINE_ADDRESS`.

Verified on-chain (2026-08-03): oracle-service pushed 12 signed price updates
(≥3 cycles, tx hashes in `/tmp/opencode/oracle-service2.log`, e.g.
`eb4c2b85...`, `90ccd3b8...`, `3f661b70...`), direct `latestPrice` reads
confirmed TOP20-AUGUST=2; a 20x long (50,000 @ 2, margin 5,000) was
liquidated at the 6.25% maintenance boundary: liquidator free balance
0 → 500 (tx `0xf979fd5433bb5539fd0baeb0ed84dec35ec3962c7b9ad0f28fb8fba03eba2400`),
trader got back 4,500 of equity.
