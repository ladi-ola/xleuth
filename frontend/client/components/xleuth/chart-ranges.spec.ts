import { describe, expect, it } from "vitest";
import { CHART_RANGES } from "./chart-ranges";

describe("chart ranges", () => {
  it("requests distinct supported candle buckets for each period", () => {
    expect(CHART_RANGES).toEqual({
      "1H": { interval: "1m", limit: 60 },
      "1D": { interval: "15m", limit: 96 },
      "1W": { interval: "4h", limit: 42 },
      "1M": { interval: "1d", limit: 30 },
    });
  });
});
