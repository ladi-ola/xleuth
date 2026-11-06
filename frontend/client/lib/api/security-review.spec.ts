import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@dynamic-labs/sdk-react-core", () => ({ getAuthToken: vi.fn() }));
vi.mock("./backend", () => ({ backendApi: { verifyToken: vi.fn() } }));

import { getAuthToken } from "@dynamic-labs/sdk-react-core";
import { backendApi } from "./backend";
import { clearInternalToken, exchangeDynamicToken } from "./token-exchange";
import { ApiError } from "./errors";

// Local evidence only: these assertions describe unsafe CURRENT behavior,
// not the desired safety contract. All tokens are inert synthetic strings.
beforeEach(() => {
  clearInternalToken();
  vi.clearAllMocks();
  vi.mocked(getAuthToken).mockReturnValue("synthetic-user-a-dynamic-token");
  vi.mocked(backendApi.verifyToken).mockResolvedValue({
    access_token: "synthetic-user-a-internal-token",
    token_type: "Bearer",
    expires_in_minutes: 60,
  });
});

describe("security review evidence (unfixed)", () => {
  it("returns the previous internal token after the SDK has signed out", async () => {
    await exchangeDynamicToken();
    vi.mocked(getAuthToken).mockReturnValue(null);
    await expect(exchangeDynamicToken()).resolves.toBe(
      "synthetic-user-a-internal-token",
    );
  });

  it("returns user A's internal token after the SDK switches to user B", async () => {
    await exchangeDynamicToken();
    vi.mocked(getAuthToken).mockReturnValue("synthetic-user-b-dynamic-token");
    await expect(exchangeDynamicToken()).resolves.toBe(
      "synthetic-user-a-internal-token",
    );
    expect(backendApi.verifyToken).toHaveBeenCalledTimes(1);
  });

  it("turns a network failure into status 500, bypassing unknown-status handling", () => {
    const error = ApiError.fromUnknown(new TypeError("Failed to fetch"));
    expect(error.status).toBe(500);
    expect(Boolean(error.status)).toBe(true);
  });
});
