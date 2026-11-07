import { useState } from "react";
import { Link } from "react-router-dom";
import { useOpenOrders, useOrderHistory, usePositions } from "@/lib/api/hooks";
import { abbreviateBasketName } from "@/lib/api/adapters";
import type { OrderListItem } from "@/lib/api/schemas";

type ActivityTab = "positions" | "open" | "history";

const activityTabs: { value: ActivityTab; label: string }[] = [
  { value: "positions", label: "Positions" },
  { value: "open", label: "Open orders" },
  { value: "history", label: "Order history" },
];

function price(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? "—" : value.toFixed(3);
}

function Orders({ orders }: { orders: OrderListItem[] }) {
  return (
    <div className="market-activity-table market-orders" role="table" aria-label="Orders">
      <div className="market-activity-row" role="row"><span role="columnheader">Basket</span><span role="columnheader">Side</span><span role="columnheader">Size</span><span role="columnheader">Type</span><span role="columnheader">Price</span><span role="columnheader">Status</span></div>
      {orders.map(order => <div className="market-activity-row" role="row" key={order.order_id}>
        <strong role="cell">{abbreviateBasketName(order.basket_name)}</strong>
        <span role="cell">{order.side === "buy" ? "Long" : "Short"}</span>
        <span role="cell">{order.size}</span>
        <span role="cell">{order.order_type.replace(/_/g, " ")}</span>
        <span role="cell">{price(order.price ?? order.average_fill_price ?? order.trigger_price)}</span>
        <span role="cell">{order.status.replace(/_/g, " ")}</span>
      </div>)}
    </div>
  );
}

/** The same authenticated queries used by Portfolio; none run while signed out. */
export function MarketActivity({ signedIn }: { signedIn: boolean }) {
  const [tab, setTab] = useState<ActivityTab>("positions");
  const positions = usePositions();
  const openOrders = useOpenOrders();
  const history = useOrderHistory();
  const selected = tab === "positions" ? positions : tab === "open" ? openOrders : history;

  return (
    <section className="market-activity terminal-card" aria-label="Your activity">
      <div className="market-activity-tabs" role="group" aria-label="Activity type">
        {activityTabs.map(item => <button key={item.value} type="button" className={tab === item.value ? "active" : ""} aria-pressed={tab === item.value} onClick={() => setTab(item.value)}>{item.label}<span>{signedIn ? item.value === "positions" ? positions.data?.positions.length ?? "—" : item.value === "open" ? openOrders.data?.orders.length ?? "—" : history.data?.orders.length ?? "—" : "—"}</span></button>)}
      </div>
      {!signedIn ? <div className="market-activity-empty"><strong>Sign in to see your activity</strong><p>Your positions and orders will appear here.</p></div>
        : selected.isPending ? <div className="market-activity-empty" role="status">Loading activity…</div>
        : selected.isError ? <div className="market-activity-empty" role="alert">Activity unavailable. Visit <Link to="/portfolio">Portfolio</Link> to retry.</div>
        : tab === "positions" ? positions.data?.positions.length ? <div className="market-activity-table" role="table" aria-label="Positions">
          <div className="market-activity-row" role="row"><span role="columnheader">Basket</span><span role="columnheader">Side</span><span role="columnheader">Size</span><span role="columnheader">Entry</span><span role="columnheader">Mark</span><span role="columnheader">PnL</span><span role="columnheader">Margin</span></div>
          {positions.data.positions.map(position => <div className="market-activity-row" role="row" key={position.position_id}>
            <strong role="cell">{abbreviateBasketName(position.basket_name)}</strong><span role="cell">{position.side === "buy" || position.side === "long" ? "Long" : "Short"} {position.leverage}×</span><span role="cell">{position.size}</span><span role="cell">{price(position.entry_price)}</span><span role="cell">{price(position.mark_price)}</span><span role="cell" className={position.unrealized_pnl_abs < 0 ? "loss" : "gain"}>${position.unrealized_pnl_abs.toFixed(2)}</span><span role="cell">${position.margin_usdc.toFixed(2)}</span>
          </div>)}
        </div> : <div className="market-activity-empty">No open positions</div>
          : tab === "open" ? openOrders.data?.orders.length ? <Orders orders={openOrders.data.orders} /> : <div className="market-activity-empty">No open orders</div>
            : history.data?.orders.length ? <Orders orders={history.data.orders} /> : <div className="market-activity-empty">No order history</div>}
      {signedIn && <Link className="market-activity-more" to="/portfolio">View and manage in Portfolio →</Link>}
    </section>
  );
}
