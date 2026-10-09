import { describe, it, expect } from "vitest";
import { queryOptions } from "./queryKeys";

// Phase 4 polling policy: authenticated reads poll no faster than the
// backend's ~5s trigger cycle, refetch on focus/reconnect, and pause while
// the browser tab is hidden (TanStack's refetchIntervalInBackground default).
describe("polling policy", () => {
  it("polls authenticated data every 10s", () => {
    expect(queryOptions.authenticated.refetchInterval).toBe(10_000);
    expect(queryOptions.authenticated.refetchInterval).toBeGreaterThanOrEqual(5_000);
  });

  it("refetches authenticated data on focus and reconnect", () => {
    expect(queryOptions.authenticated.refetchOnWindowFocus).toBe(true);
    expect(queryOptions.authenticated.refetchOnReconnect).toBe(true);
  });

  it("keeps public data on a slower cache cadence without focus refetch", () => {
    expect(queryOptions.public.staleTime).toBe(10_000);
    expect(queryOptions.public.refetchOnWindowFocus).toBe(false);
  });
});
