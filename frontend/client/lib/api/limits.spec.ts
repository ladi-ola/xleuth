import { describe, it, expect } from "vitest";
import {
  MIN_ORDER_CONTRACTS,
  minimumOrderNotional,
  formatUsdc,
} from "./limits";

describe("minimumOrderNotional", () => {
  it("converts the contract minimum into USDC at the current index price", () => {
    // 10 contracts at 30.00 index points => 300 USDC notional.
    expect(minimumOrderNotional(30)).toBe(300);
  });

  it("rounds up to the cent so the derived size stays at or above the minimum", () => {
    // 10 contracts at 43.47 => 434.70 exactly.
    expect(minimumOrderNotional(43.47)).toBe(434.7);
    // 10 contracts at 43.4711 => 434.711, rounded up to 434.72 (never below).
    expect(minimumOrderNotional(43.4711)).toBe(434.72);
  });

  it("honours an explicit contract count", () => {
    expect(minimumOrderNotional(50, 20)).toBe(1000);
  });

  it("returns 0 when there is no usable price", () => {
    expect(minimumOrderNotional(0)).toBe(0);
    expect(minimumOrderNotional(-1)).toBe(0);
    expect(minimumOrderNotional(Number.NaN)).toBe(0);
    expect(minimumOrderNotional(30, 0)).toBe(0);
  });

  it("exposes the engine's default minimum of 10 contracts", () => {
    expect(MIN_ORDER_CONTRACTS).toBe(10);
  });
});

describe("formatUsdc", () => {
  it("formats with two decimals and thousands separators", () => {
    expect(formatUsdc(434.7)).toBe("434.70");
    expect(formatUsdc(1234.5)).toBe("1,234.50");
    expect(formatUsdc(0)).toBe("0.00");
  });
});
