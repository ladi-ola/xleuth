# Xleuth Contracts (Week 3)

Foundry project for the Xleuth cash-settled dated index futures platform on
Polygon Amoy testnet.

## Contracts

| Contract              | Purpose                                                                                    |
|-----------------------|--------------------------------------------------------------------------------------------|
| `CollateralVault`     | Custody of test-USDC; per-user free vs. locked (margin) balances; OZ `SafeERC20` + `ReentrancyGuard`. Only the PositionManager may lock/release margin. |
| `PositionManager`     | Opens/closes long/short positions per user per basket_id. Margin = notional / leverage, read from the IndexOracleConsumer (must be fresh). Leverage cap is owner-settable. No liquidation/settlement yet (Week 4). |
| `IndexOracleConsumer` | Single authorized EIP-712 signer pushes `(basketId, price, timestamp)` updates; rejects unauthorized and stale updates. Prices scaled 0–100. |
| `MockUSDC`            | Testnet-only 6-decimal USDC stand-in with an open mint. Never mainnet.                     |

## Design decisions (locked)

- Margin = `(size × oracle price) / leverage`, price read live from the oracle consumer.
- Closing a position releases locked margin only — PnL realization is deferred to the Week 4 SettlementEngine.
- Trades require a fresh oracle price (within `maxStaleness`); stale prices revert.
- One net position per user per basket_id; opening opposite side on an existing position reverts.
- EIP-712 signature: `PriceUpdate(bytes32 basketId,uint256 price,uint256 timestamp)`, domain "Xleuth Index Oracle" v1.

## Usage

```bash
forge build
forge test --gas-report          # full suite incl. fuzz + gas tables
forge fmt --check

# Deploy (reads contracts/.env — gitignored, never commit real keys)
make deploy-testnet              # or: forge script script/DeployAmoy.s.sol:DeployAmoy --rpc-url $RPC_URL --broadcast

# Seed initial signed prices for ACTIVE_BASKETS
make deploy-config-baskets       # or: forge script script/ConfigureBaskets.s.sol:ConfigureBaskets --rpc-url $RPC_URL --broadcast
```

## Amoy deployments (2026-08-01)

| Contract            | Address                                                                                                            |
|---------------------|--------------------------------------------------------------------------------------------------------------------|
| CollateralVault     | `0xdd12c1434abf0f7E17c6A5281bE7c7287331eF57` |
| PositionManager     | `0xAbDa89966e620aE0332C5A23614B249ab1779e3d` |
| IndexOracleConsumer | `0xd394B8A5dace5EB22933A2a0DCE1C82c1Eb70cd2` |
| MockUSDC (test-USDC)| `0xc8783E02f3EE944BdE2990DbcDFefbe8adc3e86D` |

Verified on-chain: baskets seeded (`TOP20-JULY`=62, `TOP20-AUGUST`=48), real
deposit of 5,000 test-USDC into the vault (tx `0x34d9168c...`).
