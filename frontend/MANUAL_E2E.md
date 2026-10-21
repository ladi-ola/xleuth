# Manual end-to-end test script (testnet, Polygon Amoy)

Automated suites cover adapters, error mapping, token exchange, polling
config, WS reconnect, and the faucet client. The steps below need a browser,
a Dynamic login, and funded/connected services, so they are manual.

## Prerequisites

- `backend-api` on `http://localhost:8000`, `matching-engine` on
  `http://localhost:8001` (or the deployed HTTPS URLs from Phase 8).
- Frontend dev server (`pnpm dev`, port 8080) or the deployed origin, with
  `VITE_BACKEND_API_URL`, `VITE_MATCHING_ENGINE_URL`, `VITE_BACKEND_WS_URL`,
  `VITE_DYNAMIC_ENVIRONMENT_ID`, `VITE_COLLATERAL_TOKEN_ADDRESS`, and
  `VITE_COLLATERAL_VAULT_ADDRESS` set.
- A Dynamic account (email/social) and a little POL in the signing wallet for
  the user-signed `approve` + `deposit` transactions. The faucet funds
  test-USDC, but not gas.

## Script

1. **Sign in.** Open `/`. Confirm the markets screen loads a live basket
   list with prices and 24h change. Open a market: chart shows live
   candles, order book shows live levels, constituents expand.
2. **Get test USDC (faucet).** Go to `/portfolio`. Press **Get test USDC**.
   - Expect: "Claim Successful". Total Balance and Wallet USDC update to
     ~1,000 USDC after refetch; Vault margin stays at 0.
   - Press Get test USDC again immediately: expect "Faucet on cooldown" with
     a retry time. No duplicate claim is sent.
3. **Deposit to vault.** Press **Deposit to vault**.
   - Expect two wallet prompts: `approve` on test-USDC, then `deposit` on the
     CollateralVault. After confirmation, Wallet USDC drops to ~0 and Vault
     margin rises to ~1,000.
   - If the wallet has no POL, expect a gas error and the funds remain in the
     wallet.
4. **Place a market order.** On a market screen, Buy or Sell, enter a size
   >= ~10 contracts worth of USDC (size = notional / price; minimum
   notional ~= 10 x index price), set slippage (default 100 bps), submit.
   - Expect: "Order filled" modal for a filled order.
   - Enter a tiny size (e.g. 1 USDC): expect a clear rejection
     ("Order size is below the minimum").
5. **Position appears.** Go to `/portfolio` → Position tab: the new position
   shows with entry, current price, margin, PnL. Summary updates.
6. **Cancel an order.** Place a limit... (Limit is disabled in the UI, so:
   if a resting/open order exists from another session) press **Cancel** on
   the Open tab → "Order cancelled" and the row disappears on refetch.
   Cancelling an already-filled order surfaces the 409 message honestly.
7. **Trigger a rejection.** With no vault margin (or an unknown basket via
   devtools), submit: expect the mapped message ("Insufficient vault margin.
   Deposit test USDC from your wallet into the vault..."), never a duplicate
   order.
8. **Reload.** Refresh mid-session: sign-in persists via Dynamic, balances
   and positions reload, no crash.
9. **On-chain verification (verifier, read-only).** For each faucet claim,
   record `tx_hash`: check the claimant's test-USDC wallet balance increased
   by 1,000. For each deposit, check the wallet balance decreased and
   `CollateralVault.freeBalance(user)` increased by the same amount. Record
   order fill `tx_hash` values the same way.

## Settles (evidence to record in the report)

- 5C.2 position netting (opposite-side order: reduce/close/flip).
- 5C.3 SL/TP behavior after the position changes size.
- 5C.7 claimed USDC is visible in Wallet USDC and becomes tradeable margin
  only after **Deposit to vault** (claim → approve + deposit → place order).
