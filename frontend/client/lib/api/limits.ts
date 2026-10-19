// Matching-engine order limits.
//
// `MIN_ORDER_CONTRACTS` mirrors the engine's `MIN_ORDER_SIZE` (default 10).
// The engine's `size` field is in index units (contracts), not USDC, so the
// minimum *notional* depends on the current index price:
//   size = notional / indexPrice  =>  minNotional = MIN_ORDER_CONTRACTS * price
export const MIN_ORDER_CONTRACTS = 10;

/**
 * Smallest USDC notional that satisfies the contract-based minimum order size.
 * Rounded up to the cent so display rounding can never produce a size just
 * below the engine minimum. Returns 0 when no live price is available.
 */
export function minimumOrderNotional(
  indexPrice: number,
  minContracts: number = MIN_ORDER_CONTRACTS,
): number {
  if (!Number.isFinite(indexPrice) || indexPrice <= 0 || minContracts <= 0) {
    return 0;
  }
  return Math.ceil(indexPrice * minContracts * 100) / 100;
}

/** Format a USDC amount with thousands separators and two decimals. */
export function formatUsdc(amount: number): string {
  return amount.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}
