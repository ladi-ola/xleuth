import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { MarketActivity } from "./MarketActivity";

const fixture = vi.hoisted(() => ({ positions: [] as Record<string, string | number>[] }));
vi.mock("@/lib/api/hooks", () => ({
  usePositions: () => ({ data: { positions: fixture.positions }, isPending: false, isError: false }),
  useOpenOrders: () => ({ data: undefined, isPending: false, isError: false }),
  useOrderHistory: () => ({ data: undefined, isPending: false, isError: false }),
}));

describe("Market activity", () => {
  it("shows a sign-in prompt rather than fabricated orders or counts", () => {
    const html = renderToStaticMarkup(<MemoryRouter><MarketActivity signedIn={false} /></MemoryRouter>);
    expect(html).toContain("Sign in to see your activity");
    expect(html).toContain("Order history");
    expect(html).not.toContain("Election Momentum");
    expect(html).not.toContain("$5,000");
  });

  it("renders signed-in positions from the authenticated response", () => {
    fixture.positions = [{ position_id: "position-1", basket_name: "TOP20-APRIL-2027", side: "buy", leverage: 2, size: 100, entry_price: 3.03, mark_price: 3.079, unrealized_pnl_abs: 4.9, margin_usdc: 50 }];
    try {
      const html = renderToStaticMarkup(<MemoryRouter><MarketActivity signedIn /></MemoryRouter>);
      expect(html).toContain("TOP20-APR-2027");
      expect(html).toContain("3.079");
      expect(html).toContain("$4.90");
    } finally {
      fixture.positions = [];
    }
  });
});
