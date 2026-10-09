# Terms and Conditions — Xleuth (testnet)

> Draft from the real system audit (2026-10-09). Facts the codebase cannot know
> are marked `[[FILL: ...]]`. This is not legal advice.
> Operator: [[FILL: operator legal name]], [[FILL: contact email]].
> Governing law: [[FILL: jurisdiction / governing law]].

## 1. Testnet-only service; no monetary value; no guarantees

Xleuth is an experimental service on **Polygon Amoy testnet** using test USDC
with **no monetary value**. The service — data, balances, positions, history —
may be **reset, paused or modified at any time**, and test funds can be lost
without recourse or compensation. No uptime, correctness or availability is
promised.

## 2. No advice

Nothing in the app or docs is financial, investment or legal advice.
Leveraged index products can lose everything committed to them. Testnet
behavior predicts nothing about any future deployment.

## 3. Third-party data and oracle/settlement mechanics

- Constituent market data comes from **Polymarket/UMA public APIs** and may be
  wrong, delayed, undercounted or disputed; index values inherit those limits.
- Baskets are **linear, cash-settled, dated index futures** settling to the
  realized volume-weighted YES fraction (0–100 scale). Matching is off-chain;
  settlement/custody is on-chain via `PositionManager`/`SettlementEngine`.
- Prices are pushed by a **single operator key** (centralized by design for
  this phase); entry price on-chain is the oracle index price at match time.
- Fills confirm only when the transaction is mined. Orders may reject
  (`oracle_price_stale`, `insufficient_margin`, `basket_not_tradeable`, …).

## 4. Eligibility; restricted jurisdictions; your keys

18+ only. Not available in [[FILL: restricted/prohibited jurisdictions]].
You are solely responsible for your wallet, keys and devices. Xleuth **never
takes custody** of private keys; Dynamic embedded-wallet export is provided
by Dynamic, not us.

## 5. Acceptable use

No abuse, exploitation of bugs, market manipulation, or automated attacks
outside an agreed bug-bounty process ([[FILL: bug-bounty contact/scope]]).
We may suspend or terminate access for violations.

## 6. Fees and test funds

Faucet test USDC is free, rate-limited (24h cooldown) and may run out. No
real fees are charged on testnet. Matched trades apply the documented
`TRADING_FEE_BPS` in test USDC only.

## 7. Disclaimer and liability

To the maximum extent permitted by [[FILL: governing law]], the service is
provided **as-is, without warranties** of any kind, and liability for testnet
use is excluded to that extent. Nothing here limits liability that cannot be
limited by law.

## 8. Changes and contact

Terms may change; material changes take effect when posted here. Questions:
[[FILL: contact email]].
