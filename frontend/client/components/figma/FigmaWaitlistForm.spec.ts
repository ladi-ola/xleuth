import { afterEach, describe, expect, it, vi } from "vitest";
import { joinWaitlist } from "./FigmaWaitlistForm";

afterEach(() => vi.unstubAllGlobals());

describe("Figma waitlist request", () => {
  it("sends the approved name/email and empty honeypot without a Dynamic token", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);
    const signal = new AbortController().signal;
    await joinWaitlist("Ada Example", "ada@example.test", "", signal);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/waitlist$/),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ name: "Ada Example", email: "ada@example.test", website: "" }),
        signal,
      }),
    );
  });

  it("explains rate limiting and leaves retry to the user", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 429 }));
    await expect(joinWaitlist("Ada", "ada@example.test", "", new AbortController().signal))
      .rejects.toThrow("Too many attempts");
  });
});
