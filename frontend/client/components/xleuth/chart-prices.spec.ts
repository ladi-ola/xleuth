import { describe, expect, it } from "vitest";
import { scaleCandlesForDisplay } from "./chart-prices";

describe("chart display units", () => {
  it("scales all OHLC prices to cents without changing API candle data", () => {
    const candles = [{ time: 1794078000, open: 0.0308, high: 0.031, low: 0.0307, close: 0.03079 }];
    const [display] = scaleCandlesForDisplay(candles);
    expect(display.time).toBe(1794078000);
    expect(display.open).toBeCloseTo(3.08);
    expect(display.high).toBeCloseTo(3.1);
    expect(display.low).toBeCloseTo(3.07);
    expect(display.close).toBeCloseTo(3.079);
    expect(candles[0].close).toBe(0.03079);
  });

  it("keeps the empty chart empty", () => {
    expect(scaleCandlesForDisplay([])).toEqual([]);
  });
});
