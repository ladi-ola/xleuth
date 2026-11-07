/** Supported public candle buckets for each visible chart range. */
export const CHART_RANGES = {
  "1H": { interval: "1m", limit: 60 },
  "1D": { interval: "15m", limit: 96 },
  "1W": { interval: "4h", limit: 42 },
  "1M": { interval: "1d", limit: 30 },
} as const;

export type ChartRange = keyof typeof CHART_RANGES;
