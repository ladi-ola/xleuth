import { describe, expect, it } from "vitest";

import {
  buildAllowanceCalldata,
  buildApproveCalldata,
  buildBalanceOfCalldata,
  buildDepositCalldata,
  buildFreeBalanceCalldata,
  toUsdcUnits,
} from "./contracts";

const VAULT = "0x6dbeEb6a5bE0cD63159b1dBD5525dE125A1CECef";

describe("USDC amount conversion", () => {
  it("scales USDC to 6-decimal token units", () => {
    expect(toUsdcUnits(1)).toBe(1_000_000n);
    expect(toUsdcUnits(1000)).toBe(1_000_000_000n);
    expect(toUsdcUnits(0.000001)).toBe(1n);
  });

  it("returns zero for non-positive or invalid amounts", () => {
    expect(toUsdcUnits(0)).toBe(0n);
    expect(toUsdcUnits(-5)).toBe(0n);
    expect(toUsdcUnits(Number.NaN)).toBe(0n);
  });
});

describe("CollateralVault calldata", () => {
  it("encodes approve(address,uint256)", () => {
    const amount = 1_000_000_000n; // 1,000 USDC
    expect(buildApproveCalldata(VAULT, amount)).toBe(
      "0x095ea7b3" +
        "0".repeat(24) +
        VAULT.toLowerCase().slice(2) +
        amount.toString(16).padStart(64, "0"),
    );
  });

  it("encodes deposit(uint256)", () => {
    const amount = 1_000_000_000n;
    expect(buildDepositCalldata(amount)).toBe(
      "0xb6b55f25" + amount.toString(16).padStart(64, "0"),
    );
  });

  it("encodes balanceOf(address)", () => {
    expect(buildBalanceOfCalldata(VAULT)).toBe(
      "0x70a08231" + "0".repeat(24) + VAULT.toLowerCase().slice(2),
    );
  });

  it("encodes allowance(address,address)", () => {
    const owner = "0x6Aba39d2E2d108B964D099C4ae476bf474Be78B1";
    expect(buildAllowanceCalldata(owner, VAULT)).toBe(
      "0xdd62ed3e" +
        "0".repeat(24) +
        owner.toLowerCase().slice(2) +
        "0".repeat(24) +
        VAULT.toLowerCase().slice(2),
    );
  });

  it("encodes freeBalance(address)", () => {
    expect(buildFreeBalanceCalldata(VAULT)).toBe(
      "0x95b881de" + "0".repeat(24) + VAULT.toLowerCase().slice(2),
    );
  });
});
