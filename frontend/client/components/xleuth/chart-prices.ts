/** Candle API prices are unscaled; the displayed index and order book use cents (×100). */
export const INDEX_PRICE_DISPLAY_SCALE = 100;

export type ChartCandle = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
};

export function scaleCandlesForDisplay(candles: readonly ChartCandle[]): ChartCandle[] {
  return candles.map(({ time, open, high, low, close }) => ({
    time,
    open: open * INDEX_PRICE_DISPLAY_SCALE,
    high: high * INDEX_PRICE_DISPLAY_SCALE,
    low: low * INDEX_PRICE_DISPLAY_SCALE,
    close: close * INDEX_PRICE_DISPLAY_SCALE,
  }));
}
