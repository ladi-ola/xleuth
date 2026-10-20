// Matching-engine order limits.
//
// `MIN_ORDER_USDC` mirrors the engine's `MIN_ORDER_SIZE` (default 10). It is a
// minimum *notional* in USDC, not a contract count: the engine computes
// notional = indexPrice * size, so the contract floor depends on the price.
export const MIN_ORDER_USDC = 10;

/** Format a USDC amount with thousands separators and two decimals. */
export function formatUsdc(amount: number): string {
  return amount.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}
