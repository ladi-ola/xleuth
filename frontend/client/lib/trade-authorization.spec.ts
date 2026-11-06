import { describe, expect, it, vi } from "vitest";
import {
  authorizationDigest,
  authorizationTypedData,
  closingIntent,
  exactUnits,
  MAX_NOTIONAL_UNITS,
  MIN_NOTIONAL_UNITS,
  notionalUnits,
  openingIntent,
  priceUnits,
  signAuthorization,
  sizeUnits,
  validateAuthorization,
  type TradeAuthorization,
} from "./trade-authorization";

const executor = `0x${"22".repeat(20)}` as const;
const expectedDigest =
  "0xdd4cdf2bedcadb6766b94138db28b3435cc8602f7cfe3efa8c97c4e1a4e877e7";

it('matches the Python and Solidity opening-intent ABI preimage', () => {
  const { intent, orderId } = openingIntent({
    kind: 'market', salt: `0x${'11'.repeat(32)}`,
  });
  expect(intent.length).toBe(322);
  expect(orderId).toBe('0x5fe93c1d89d9c4441652283279590608382468d4df587182c5203d38bd234219');
  expect(() => openingIntent({ kind: 'stop', salt: `0x${'11'.repeat(32)}` }))
    .toThrow('trigger');
});

it('binds a bracket close to a lot, trigger and OCO group', () => {
  const signed = closingIntent({
    kind: 'stop_loss', positionId: `0x${'0'.repeat(63)}1`,
    salt: `0x${'11'.repeat(32)}`, triggerPrice: 50_000n,
    ocoGroup: `0x${'22'.repeat(32)}`,
  });
  expect(signed.intent.length).toBe(322);
  expect(signed.intent.slice(2 + 128, 2 + 192)).toBe('22'.repeat(32));
  expect(() => closingIntent({
    kind: 'take_profit', positionId: `0x${'0'.repeat(63)}1`,
    salt: `0x${'11'.repeat(32)}`, triggerPrice: 50_000n,
  })).toThrow('OCO');
});

function authorization(
  changes: Partial<TradeAuthorization> = {},
): TradeAuthorization {
  return {
    trader: `0x${"11".repeat(20)}`,
    basketId: `0x${"aa".repeat(32)}`,
    orderId: `0x${"bb".repeat(32)}`,
    side: 0,
    size: 1_234_567n,
    maxNotional: 100_000_000n,
    minPrice: 50_000n,
    maxPrice: 50_001n,
    leverage: 3n,
    nonce: (1n << 80n) + 7n,
    deadline: 2_000_000_000n,
    fillOrKill: false,
    reduceOnly: false,
    positionId: `0x${"00".repeat(32)}`,
    ...changes,
  };
}

describe("V2 signed execution envelope", () => {
  it("matches the Python/Solidity EIP-712 vector, including a >53-bit nonce", () => {
    expect(authorizationDigest(80002, executor, authorization())).toBe(
      expectedDigest,
    );
  });

  it("binds chain, executor and every signed field", () => {
    const original = authorizationDigest(80002, executor, authorization());
    const variants: Partial<TradeAuthorization>[] = [
      { trader: `0x${"33".repeat(20)}` },
      { basketId: `0x${"cc".repeat(32)}` },
      { orderId: `0x${"dd".repeat(32)}` },
      { side: 1 },
      { size: 1_234_568n },
      { maxNotional: 100_000_001n },
      { minPrice: 49_999n },
      { maxPrice: 50_002n },
      { leverage: 4n },
      { nonce: 7n },
      { deadline: 2_000_000_001n },
      { fillOrKill: true },
      { positionId: `0x${"ee".repeat(32)}` },
      { reduceOnly: true, positionId: `0x${"ee".repeat(32)}` },
    ];
    for (const change of variants) {
      expect(
        authorizationDigest(80002, executor, authorization(change)),
      ).not.toBe(original);
    }
    expect(authorizationDigest(80003, executor, authorization())).not.toBe(
      original,
    );
    expect(
      authorizationDigest(80002, `0x${"44".repeat(20)}`, authorization()),
    ).not.toBe(original);
  });

  it("has exact price, contract and USDC units", () => {
    expect(priceUnits("50.123")).toBe(50_123n);
    expect(sizeUnits("0.200000")).toBe(200_000n);
    expect(exactUnits("0.123456000", 6)).toBe(123_456n);
    expect(notionalUnits(200_000n, 50_123n)).toBe(10_024_600n);
    expect(notionalUnits(1n, 1n)).toBe(1n);
    expect(notionalUnits(1n, 1n, false)).toBe(0n);
  });

  it.each(["NaN", "Infinity", "-1", "0", "1e99999", "0.1234567"])(
    "rejects invalid or excess-precision sizes (%s)",
    (value) => {
      expect(() => sizeUnits(value)).toThrow();
    },
  );

  it("rejects excess price precision and out-of-range prices", () => {
    expect(() => priceUnits("50.1234")).toThrow();
    expect(() => priceUnits("100.001")).toThrow();
  });

  it("accepts the $10 and $1,000 budgets, rejects values outside them", () => {
    expect(() =>
      validateAuthorization(authorization({ maxNotional: MIN_NOTIONAL_UNITS })),
    ).not.toThrow();
    expect(() =>
      validateAuthorization(authorization({ maxNotional: MAX_NOTIONAL_UNITS })),
    ).not.toThrow();
    expect(() =>
      validateAuthorization(
        authorization({ maxNotional: MIN_NOTIONAL_UNITS - 1n }),
      ),
    ).toThrow();
    expect(() =>
      validateAuthorization(
        authorization({ maxNotional: MAX_NOTIONAL_UNITS + 1n }),
      ),
    ).toThrow();
  });

  it("requires reduce-only to identify a position", () => {
    expect(() =>
      validateAuthorization(authorization({ reduceOnly: true })),
    ).toThrow();
  });

  it("signs using the existing wallet without transmitting a private key", async () => {
    const a = authorization();
    const client = {
      account: { address: a.trader },
      request: vi.fn().mockResolvedValue("0x13882"),
      signTypedData: vi.fn().mockResolvedValue("0x1234"),
    };
    await expect(
      signAuthorization({ client, authorization: a, chainId: 80002, executor }),
    ).resolves.toBe("0x1234");
    expect(client.signTypedData).toHaveBeenCalledWith({
      ...authorizationTypedData(80002, executor, a),
      account: a.trader,
    });
  });

  it("preserves large integers when using eth_signTypedData_v4", async () => {
    const a = authorization();
    const client = {
      account: { address: a.trader },
      request: vi
        .fn()
        .mockResolvedValueOnce("0x13882")
        .mockResolvedValueOnce("0x1234"),
    };
    await signAuthorization({
      client,
      authorization: a,
      chainId: 80002,
      executor,
    });
    const call = client.request.mock.calls[1][0];
    expect(call.method).toBe("eth_signTypedData_v4");
    expect(JSON.parse(call.params[1]).message.nonce).toBe(a.nonce.toString());
    expect(JSON.parse(call.params[1]).types.EIP712Domain).toHaveLength(4);
  });

  it("refuses a different wallet or chain, without attempting to sign", async () => {
    const a = authorization();
    const client = {
      account: { address: `0x${"33".repeat(20)}` },
      request: vi.fn().mockResolvedValue("0x1"),
      signTypedData: vi.fn(),
    };
    await expect(
      signAuthorization({ client, authorization: a, chainId: 80002, executor }),
    ).rejects.toThrow("wallet");
    client.account.address = a.trader;
    await expect(
      signAuthorization({ client, authorization: a, chainId: 80002, executor }),
    ).rejects.toThrow("network");
    expect(client.signTypedData).not.toHaveBeenCalled();
  });

  it("propagates wallet rejection without retries or fallback signing", async () => {
    const a = authorization();
    const rejected = Object.assign(new Error("User rejected"), { code: 4001 });
    const client = {
      account: { address: a.trader },
      request: vi.fn().mockResolvedValue("0x13882"),
      signTypedData: vi.fn().mockRejectedValue(rejected),
    };
    await expect(
      signAuthorization({ client, authorization: a, chainId: 80002, executor }),
    ).rejects.toBe(rejected);
    expect(client.signTypedData).toHaveBeenCalledTimes(1);
    expect(client.request).toHaveBeenCalledTimes(1);
  });
});
