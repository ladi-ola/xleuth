import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { backendApi } from "./backend";

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (name: string) => headers[name] ?? null },
    json: async () => body,
  } as unknown as Response;
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(jsonResponse(200, { tx_hash: "0xabc", status: "submitted" }))
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("claimFaucet", () => {
  it("returns the tx hash on success", async () => {
    const result = await backendApi.claimFaucet("token", "0x" + "a".repeat(40));
    expect(result.tx_hash).toBe("0xabc");
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1);
    const [, options] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    expect((options.headers as Record<string, string>)["Authorization"]).toBe("Bearer token");
    expect(JSON.parse(options.body as string)).toEqual({
      smart_account_address: "0x" + "a".repeat(40),
    });
  });

  it("parses cooldown from the Retry-After header", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(429, { detail: "Faucet claim on cooldown" }, { "Retry-After": "3600" })
    );
    const error = await backendApi
      .claimFaucet("token", "0x" + "a".repeat(40))
      .catch((e) => e);
    expect(error.status).toBe(429);
    expect(error.retryAfter).toBe(3600);
  });

  it("falls back to zero retryAfter when the header is absent", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(429, { detail: "Faucet claim on cooldown" })
    );
    const error = await backendApi
      .claimFaucet("token", "0x" + "a".repeat(40))
      .catch((e) => e);
    expect(error.status).toBe(429);
    expect(error.retryAfter).toBe(0);
  });

  it("surfaces chain failures without retrying", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse(500, { detail: "Transaction failed: boom" })
    );
    const error = await backendApi
      .claimFaucet("token", "0x" + "a".repeat(40))
      .catch((e) => e);
    expect(error.status).toBe(500);
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1);
  });

  it("propagates 401 auth failures for the token bridge", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(401, { detail: "token_expired" }));
    const error = await backendApi
      .claimFaucet("token", "0x" + "a".repeat(40))
      .catch((e) => e);
    expect(error.status).toBe(401);
  });

  it("propagates network errors untouched (callers must not retry)", async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError("fetch failed"));
    await expect(backendApi.claimFaucet("token", "0x" + "a".repeat(40))).rejects.toThrow(
      "fetch failed"
    );
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1);
  });
});
