// Shared number formatting for price deltas and percentage deltas.
//
// One place decides the precision and edge-case behaviour so every surface
// (Explore cards, index header, positions) renders identically. Values are
// always fixed to 3 decimals with an explicit sign; null/undefined/NaN and
// non-finite numbers render as a dash, and scientific notation is never
// produced. Do NOT use this for other kinds of numbers (balances, prices,
// fees) - those keep their own formatting.

/** Fixed decimal places for delta / percent-delta values. */
export const DELTA_DECIMALS = 3;

/** Rendered when a delta is absent or invalid. */
export const DELTA_FALLBACK = "\u2014"; // em dash

/**
 * `Number.prototype.toFixed` switches to exponential notation for magnitudes
 * >= 1e21. Price/percentage deltas are never that large, but we guarantee
 * non-scientific output regardless.
 */
function toFixedNoExponent(value: number, decimals: number): string {
  const fixed = value.toFixed(decimals);
  if (!fixed.includes("e") && !fixed.includes("E")) {
    return fixed;
  }
  return value.toLocaleString("en-US", {
    useGrouping: false,
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function formatSigned(
  value: number | null | undefined,
  decimals: number,
  suffix: string,
): string {
  if (value === null || value === undefined) {
    return DELTA_FALLBACK;
  }
  const n = Number(value);
  if (!Number.isFinite(n)) {
    return DELTA_FALLBACK;
  }
  const sign = n >= 0 ? "+" : "-";
  return `${sign}${toFixedNoExponent(Math.abs(n), decimals)}${suffix}`;
}

/** Format an absolute price delta, e.g. `0.52` -> `+0.520`, `-1.2` -> `-1.200`. */
export function formatDelta(value: number | null | undefined): string {
  return formatSigned(value, DELTA_DECIMALS, "");
}

/** Format a percentage delta, e.g. `1.43211` -> `+1.432%`. */
export function formatPercentDelta(value: number | null | undefined): string {
  return formatSigned(value, DELTA_DECIMALS, "%");
}
