import { describe, it, expect } from "vitest";
import { MIN_ORDER_USDC, formatUsdc } from "./limits";

describe("MIN_ORDER_USDC", () => {
  it("mirrors the engine's 10 USDC minimum notional", () => {
    expect(MIN_ORDER_USDC).toBe(10);
  });
});

describe("formatUsdc", () => {
  it("formats with two decimals and thousands separators", () => {
    expect(formatUsdc(10)).toBe("10.00");
    expect(formatUsdc(434.7)).toBe("434.70");
    expect(formatUsdc(1234.5)).toBe("1,234.50");
    expect(formatUsdc(0)).toBe("0.00");
  });
});
