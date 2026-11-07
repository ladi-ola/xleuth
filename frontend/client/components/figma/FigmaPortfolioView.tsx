import { Download, Upload } from "lucide-react";
import { useDynamicContext } from "@dynamic-labs/sdk-react-core";
import { formatPercentDelta } from "@/lib/format";
import type { PositionResponse } from "@/lib/api/schemas";
import type { Position, OpenOrder, HistoryOrder } from "@/lib/portfolio-data";
import { OpenOrderCard } from "@/components/xleuth/OpenOrderCard";
import { HistoryCard } from "@/components/xleuth/HistoryCard";
import "./account-portfolio.css";

export type PortfolioTab = "position" | "open" | "history";

type Summary = {
  totalBalance: number;
  unrealizedPnl: number;
  freeMargin: number;
  usedMargin: number;
  profitLoss: number;
  walletBalance: number;
};

function dollars(amount: number | null | undefined) {
  return amount == null || !Number.isFinite(amount) ? "—" : `$${amount.toFixed(2)}`;
}

function nullablePrice(amount: number | null | undefined) {
  return amount == null || !Number.isFinite(amount) ? "—" : amount.toFixed(3);
}

export function FigmaPortfolioView({ tab, onTabChange, summary, positions, rawPositions, openOrders, historyOrders, isCancelling, onCancel, isClaiming, isDepositing, onClaim, onDeposit, onWithdraw }: {
  tab: PortfolioTab;
  onTabChange: (tab: PortfolioTab) => void;
  summary: Summary | null;
  positions: Position[];
  rawPositions: PositionResponse[];
  openOrders: OpenOrder[];
  historyOrders: HistoryOrder[];
  isCancelling: boolean;
  onCancel: (orderId: string) => void;
  isClaiming: boolean;
  isDepositing: boolean;
  onClaim: () => void;
  onDeposit: () => void;
  onWithdraw: () => void;
}) {
  const { user, setShowAuthFlow } = useDynamicContext();
  if (!user) return (
    <div className="app-page centered-page figma-account-portfolio">
      <div className="auth-prompt"><span className="account-orb">X</span><h1>Your portfolio, in one view.</h1><p>Sign in to view balances, positions, and order history.</p><button type="button" className="app-primary" onClick={() => setShowAuthFlow(true)}>Sign in</button></div>
    </div>
  );

  const values = [
    ["Balance", dollars(summary?.totalBalance), "USDC"],
    ["Vault margin", dollars(summary?.freeMargin), "Available"],
    ["Margin used", dollars(summary?.usedMargin), "USDC"],
    ["Unrealized PnL", dollars(summary?.unrealizedPnl), "USDC"],
  ] as const;
  const originalById = new Map(rawPositions.map(position => [position.position_id, position]));

  return (
    <div className="app-page figma-account-portfolio">
      <div className="page-heading"><div><span className="app-kicker">Overview</span><h1>Portfolio</h1><p>Your testnet balance and active exposure.</p></div></div>
      <div className="summary-grid">{values.map(([label, value, note]) => <article className="summary-card terminal-card" key={label}><span>{label}</span><strong className={label === "Unrealized PnL" && (summary?.unrealizedPnl ?? 0) < 0 ? "loss" : label === "Unrealized PnL" && summary ? "gain" : ""}>{value}</strong><small>{note}</small></article>)}</div>
      <section className="portfolio-funds terminal-card" aria-label="Testnet funds">
        <div><span>Wallet USDC</span><strong>{dollars(summary?.walletBalance)}</strong></div>
        <div><span>Profit/Loss</span><strong>{dollars(summary?.profitLoss)}</strong></div>
        <div className="portfolio-fund-actions"><button type="button" onClick={onClaim} disabled={isClaiming || isDepositing}><Download size={14} />{isClaiming ? "Claiming..." : "Get test USDC"}</button><button type="button" onClick={onDeposit} disabled={isDepositing || isClaiming}><Upload size={14} />{isDepositing ? "Depositing..." : "Deposit to vault"}</button><button type="button" onClick={onWithdraw} disabled><Download size={14} />Withdraw</button></div>
        <p>Only vault margin can back orders. Depositing moves your wallet test-USDC into the CollateralVault. Keep a little Amoy POL in this wallet for the approval and deposit gas.</p>
      </section>
      <section className="portfolio-table terminal-card" aria-label="Portfolio activity">
        <div className="data-tabs" role="group" aria-label="Portfolio activity type">
          {([{ value: "position", label: "Positions", count: positions.length }, { value: "open", label: "Open orders", count: openOrders.length }, { value: "history", label: "History", count: historyOrders.length }] as const).map(item => <button key={item.value} type="button" className={tab === item.value ? "active" : ""} aria-pressed={tab === item.value} onClick={() => onTabChange(item.value)}>{item.label}<span>{item.count}</span></button>)}
        </div>
        {tab === "position" ? positions.length ? <div className="portfolio-data" role="table" aria-label="Positions">
          <div className="table-head" role="row"><span role="columnheader">Basket</span><span role="columnheader">Direction</span><span role="columnheader">Size</span><span role="columnheader">Entry</span><span role="columnheader">Mark</span><span role="columnheader">PnL</span><span role="columnheader">Leverage</span><span role="columnheader">Opened</span></div>
          {positions.map(position => <div role="rowgroup" key={position.id}><div className="table-row" role="row"><strong role="cell">{position.symbol}</strong><span role="cell" className={position.side === "LONG" ? "gain" : "loss"}>{position.side}</span><span role="cell">{position.size}</span><span role="cell">{nullablePrice(position.entry)}</span><span role="cell">{nullablePrice(position.current)}</span><span role="cell" className={position.pnlAbs < 0 ? "loss" : "gain"}>{formatPercentDelta(position.pnlPct)} · {dollars(position.pnlAbs)}</span><span role="cell">{position.leverage}</span><span role="cell">{position.openedAt}</span></div>
            <div className="position-extra" role="group" aria-label={`Risk details for ${position.symbol}`}><span>Margin {dollars(position.margin)}</span><span>Liq. Price {nullablePrice(originalById.get(position.id)?.liquidation_price)}</span><span>S/L {nullablePrice(originalById.get(position.id)?.stop_loss_price)}</span><span>T/P {nullablePrice(originalById.get(position.id)?.take_profit_price)}</span><span>Fee {originalById.get(position.id)?.fee_paid ?? "—"}</span></div>
          </div>)}
        </div> : <div className="portfolio-empty"><h2>No open positions</h2><p>Your running positions show here</p></div>
          : tab === "open" ? openOrders.length ? <div className="portfolio-card-list">{openOrders.map(order => <OpenOrderCard key={order.id} order={order} onCancel={onCancel} cancelling={isCancelling} />)}</div> : <div className="portfolio-empty"><h2>No open orders</h2><p>Your limit orders show here</p></div>
          : historyOrders.length ? <div className="portfolio-card-list">{historyOrders.map(order => <HistoryCard key={order.id} order={order} />)}</div> : <div className="portfolio-empty"><h2>No trade history</h2><p>Your closed trades show here</p></div>}
      </section>
    </div>
  );
}
