import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@dynamic-labs/sdk-react-core", () => ({
  getAuthToken: vi.fn(),
}));

vi.mock("./backend", () => ({
  backendApi: { verifyToken: vi.fn() },
}));

import { getAuthToken } from "@dynamic-labs/sdk-react-core";
import { backendApi } from "./backend";
import {
  exchangeDynamicToken,
  authenticatedFetch,
  clearInternalToken,
} from "./token-exchange";

const mockGetAuthToken = vi.mocked(getAuthToken);
const mockVerifyToken = vi.mocked(backendApi.verifyToken);

beforeEach(() => {
  clearInternalToken();
  vi.clearAllMocks();
  mockGetAuthToken.mockReturnValue("dynamic-jwt");
  mockVerifyToken.mockResolvedValue({
    access_token: "internal-token",
    token_type: "Bearer",
    expires_in_minutes: 60,
  });
});

describe("exchangeDynamicToken", () => {
  it("exchanges the Dynamic JWT once and caches the internal token", async () => {
    await expect(exchangeDynamicToken()).resolves.toBe("internal-token");
    await expect(exchangeDynamicToken()).resolves.toBe("internal-token");
    expect(mockVerifyToken).toHaveBeenCalledTimes(1);
    expect(mockVerifyToken).toHaveBeenCalledWith("dynamic-jwt");
  });

  it("throws token_missing when no Dynamic token exists", async () => {
    mockGetAuthToken.mockReturnValue(null);
    await expect(exchangeDynamicToken()).rejects.toMatchObject({
      status: 401,
      code: "token_missing",
    });
  });

  it("re-exchanges after the cached token expires", async () => {
    mockVerifyToken.mockResolvedValueOnce({
      access_token: "short-lived",
      token_type: "Bearer",
      expires_in_minutes: 0,
    });
    await expect(exchangeDynamicToken()).resolves.toBe("short-lived");
    await expect(exchangeDynamicToken()).resolves.toBe("internal-token");
    expect(mockVerifyToken).toHaveBeenCalledTimes(2);
  });
});

describe("authenticatedFetch", () => {
  it("retries once after token_expired and then succeeds", async () => {
    const fetchFn = vi
      .fn()
      .mockRejectedValueOnce(
        Object.assign(new Error("expired"), { status: 401, code: "token_expired" })
      )
      .mockResolvedValueOnce("ok");
    await expect(authenticatedFetch(fetchFn)).resolves.toBe("ok");
    expect(fetchFn).toHaveBeenCalledTimes(2);
  });

  it("never loops: throws after one retry on repeated 401", async () => {
    const fetchFn = vi
      .fn()
      .mockRejectedValue(
        Object.assign(new Error("invalid"), { status: 401, code: "token_invalid" })
      );
    await expect(authenticatedFetch(fetchFn)).rejects.toMatchObject({
      code: "token_invalid",
    });
    expect(fetchFn).toHaveBeenCalledTimes(2);
  });

  it("does not retry non-401 errors", async () => {
    const fetchFn = vi
      .fn()
      .mockRejectedValue(Object.assign(new Error("x"), { status: 422 }));
    await expect(authenticatedFetch(fetchFn)).rejects.toMatchObject({ status: 422 });
    expect(fetchFn).toHaveBeenCalledTimes(1);
  });
});
