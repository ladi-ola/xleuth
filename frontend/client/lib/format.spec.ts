import { describe, it, expect } from "vitest";
import {
  DELTA_FALLBACK,
  formatDelta,
  formatPercentDelta,
} from "./format";

describe("formatDelta", () => {
  it("renders 3 decimals regardless of input precision", () => {
    expect(formatDelta(0.519999999999996)).toBe("+0.520");
    expect(formatDelta(0.22)).toBe("+0.220");
    expect(formatDelta(0)).toBe("+0.000");
  });

  it("preserves the sign", () => {
    expect(formatDelta(-1.25)).toBe("-1.250");
    expect(formatDelta(2.38)).toBe("+2.380");
  });

  it("rounds to 3 decimals", () => {
    expect(formatDelta(0.12349)).toBe("+0.123");
    expect(formatDelta(1.23456)).toBe("+1.235");
  });

  it("renders a dash for null, undefined, NaN and Infinity", () => {
    expect(formatDelta(null)).toBe(DELTA_FALLBACK);
    expect(formatDelta(undefined)).toBe(DELTA_FALLBACK);
    expect(formatDelta(Number.NaN)).toBe(DELTA_FALLBACK);
    expect(formatDelta(Number.POSITIVE_INFINITY)).toBe(DELTA_FALLBACK);
    expect(formatDelta(Number.NEGATIVE_INFINITY)).toBe(DELTA_FALLBACK);
  });

  it("never outputs scientific notation", () => {
    expect(formatDelta(1e-7)).toBe("+0.000");
    expect(formatDelta(1e21)).not.toMatch(/e/i);
    expect(formatDelta(-1e21)).not.toMatch(/e/i);
    expect(formatDelta(-1e21)).toBe("-1000000000000000000000.000");
  });
});

describe("formatPercentDelta", () => {
  it("appends a percent sign with 3 decimals", () => {
    expect(formatPercentDelta(1.4321123657394548)).toBe("+1.432%");
    expect(formatPercentDelta(0)).toBe("+0.000%");
  });

  it("preserves the sign", () => {
    expect(formatPercentDelta(-17.1)).toBe("-17.100%");
    expect(formatPercentDelta(0.57)).toBe("+0.570%");
  });

  it("renders a dash for invalid values", () => {
    expect(formatPercentDelta(null)).toBe(DELTA_FALLBACK);
    expect(formatPercentDelta(undefined)).toBe(DELTA_FALLBACK);
    expect(formatPercentDelta(Number.NaN)).toBe(DELTA_FALLBACK);
  });
});
