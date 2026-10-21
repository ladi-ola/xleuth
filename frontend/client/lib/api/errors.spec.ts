import { describe, it, expect } from "vitest";
import { getRejectionMessage, parseApiError, ApiError } from "./errors";

function apiError(status: number, data?: unknown, extra?: Record<string, unknown>) {
  return Object.assign(new Error(`API Error: ${status}`), { status, data }, extra);
}

describe("getRejectionMessage", () => {
  it("maps known rejection codes to user-facing messages", () => {
    expect(getRejectionMessage("insufficient_margin")).toContain("margin");
    expect(getRejectionMessage("size_below_min")).toContain("minimum");
    expect(getRejectionMessage("size_below_min")).toContain("10 USDC");
  });

  it("maps auth codes to sign-in messages", () => {
    expect(getRejectionMessage("token_expired")).toContain("expired");
  });

  it("falls back to a generic message that still shows the code", () => {
    expect(getRejectionMessage("some_future_code")).toContain("some_future_code");
  });
});

describe("parseApiError", () => {
  it("parses 401 token codes", () => {
    const parsed = parseApiError(apiError(401, { detail: "token_expired" }));
    expect(parsed.code).toBe("token_expired");
    expect(parsed.status).toBe(401);
  });

  it("parses 403 as unauthorized", () => {
    const parsed = parseApiError(apiError(403, { detail: "not your order" }));
    expect(parsed.status).toBe(403);
    expect(parsed.message).toContain("not authorized");
  });

  it("parses 422 rejection-code details", () => {
    const parsed = parseApiError(apiError(422, { detail: "insufficient_margin" }));
    expect(parsed.code).toBe("insufficient_margin");
    expect(parsed.message).toContain("margin");
  });

  it("parses rejection codes that the engine suffixes with details", () => {
    const parsed = parseApiError(
      apiError(422, {
        detail:
          "insufficient_margin ({'required_usdc': 10.0, 'free_usdc': 0.0})",
      })
    );
    expect(parsed.code).toBe("insufficient_margin");
    expect(parsed.message).toContain("vault margin");
  });

  it("parses FastAPI validation-error arrays", () => {
    const parsed = parseApiError(
      apiError(422, { detail: [{ loc: ["body", "size"], msg: "bad", type: "x" }] })
    );
    expect(parsed.validationErrors).toEqual([{ field: "size", message: "bad" }]);
  });

  it("parses 429 cooldown with retryAfter", () => {
    const parsed = parseApiError(apiError(429, { retry_after: 3600 }, { retryAfter: 3600 }));
    expect(parsed.code).toBe("cooldown");
    expect(parsed.retryAfter).toBe(3600);
  });

  it("surfaces 404/409 detail strings as-is", () => {
    expect(parseApiError(apiError(404, { detail: "order not found" })).message).toBe(
      "order not found"
    );
    expect(parseApiError(apiError(409, { detail: "already filled" })).message).toBe(
      "already filled"
    );
  });
});

describe("ApiError", () => {
  it("flags auth errors and single-retry eligibility", () => {
    const expired = new ApiError("x", { status: 401, code: "token_expired" });
    expect(expired.isAuthError()).toBe(true);
    expect(expired.isRetryable()).toBe(true);
    const missing = new ApiError("x", { status: 401, code: "token_missing" });
    expect(missing.isRetryable()).toBe(false);
    const server = new ApiError("x", { status: 500 });
    expect(server.isAuthError()).toBe(false);
    expect(server.isRetryable()).toBe(false);
    expect(server.isCooldown()).toBe(false);
  });

  it("flags cooldowns", () => {
    expect(new ApiError("x", { status: 429 }).isCooldown()).toBe(true);
  });
});
