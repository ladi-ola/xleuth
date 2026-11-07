import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import type { Position } from "@/lib/portfolio-data";
import type { PositionResponse } from "@/lib/api/schemas";
import { PortfolioView } from "./PortfolioView";

vi.mock("@dynamic-labs/sdk-react-core", () => ({ useDynamicContext: () => ({ user: { userId: "test-user" }, setShowAuthFlow: vi.fn() }) }));

const position: Position = {
  id: "test-position", symbol: "TEST", side: "LONG", leverage: "2x Leverage",
  pnlPct: 1.23456, pnlAbs: 2, size: 3, entry: 50, current: 51,
  margin: 10, liqPrice: 0, sl: 0, tp: 0, fee: "—", openedAt: "Nov 7, 2026",
};
const raw: PositionResponse = {
  position_id: "test-position", basket_name: "TEST", side: "buy", size: 3,
  leverage: 2, entry_price: 50, mark_price: 51, margin_usdc: 10,
  liquidation_price: null, unrealized_pnl_abs: 2, unrealized_pnl_pct: 1.23456,
  stop_loss_price: null, take_profit_price: null, stop_loss_order_id: null,
  take_profit_order_id: null, oco_group_id: null, fee_paid: null,
  opened_at: "2026-11-07T00:00:00Z",
};

describe("Figma portfolio presentation", () => {
  it("shows unavailable nullable position values, not the adapter's zero placeholders", () => {
    const markup = renderToStaticMarkup(<PortfolioView
      tab="position" onTabChange={vi.fn()} summary={null} positions={[position]}
      rawPositions={[raw]} openOrders={[]} historyOrders={[]}
      isCancelling={false} onCancel={vi.fn()} isClaiming={false}
      isDepositing={false} onClaim={vi.fn()} onDeposit={vi.fn()} onWithdraw={vi.fn()}
    />);
    expect(markup).toContain("+1.235%");
    expect(markup).toContain("Liq. Price —");
    expect(markup).toContain("S/L —");
    expect(markup).toContain("T/P —");
    expect(markup).toContain("Fee —");
    expect(markup).not.toContain("Liq. Price 0.000");
    expect(markup).toContain("Balance");
  });
});
