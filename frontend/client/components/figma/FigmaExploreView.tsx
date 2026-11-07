import { Link } from "react-router-dom";
import { Search } from "lucide-react";
import type { Basket, BasketStatus } from "@/lib/market-data";
import { formatPercentDelta } from "@/lib/format";
import "./explore.css";

const statuses: { value: BasketStatus; label: string }[] = [
  { value: "active", label: "Active" },
  { value: "upcoming", label: "Upcoming" },
  { value: "resolved", label: "Resolved" },
];

/** Displays only API-backed baskets, keeping the page's existing query/adapters. */
export function FigmaExploreView({ tab, onTabChange, query, onQueryChange, baskets, isLoading, isError, onRetry }: {
  tab: BasketStatus;
  onTabChange: (value: BasketStatus) => void;
  query: string;
  onQueryChange: (value: string) => void;
  baskets: Basket[];
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
}) {
  return (
    <div className="app-page figma-explore">
      <div className="page-heading">
        <div><span className="app-kicker">Discover</span><h1>Explore baskets</h1><p>Prediction-market indices built around a single thesis.</p></div>
        <span className="testnet-pill">Testnet data</span>
      </div>
      <div className="explore-tools">
        <label className="search-field"><Search size={16} aria-hidden="true" /><input type="search" aria-label="Search baskets" value={query} onChange={event => onQueryChange(event.target.value)} placeholder="Search by basket or ticker" /></label>
        <button className="app-ghost" type="button" disabled title="Live basket data refreshes automatically">Refresh</button>
      </div>
      <div className="explore-statuses" role="group" aria-label="Market status">
        {statuses.map(({ value, label }) => <button key={value} type="button" aria-pressed={tab === value} className={tab === value ? "active" : ""} onClick={() => onTabChange(value)}>{label}</button>)}
      </div>

      {isLoading ? <div className="loading-grid" role="status" aria-label="Loading baskets"><i /><i /><i /><i /></div>
        : isError ? <div className="state-card" role="alert"><span aria-hidden="true">!</span><h2>Couldn’t load baskets</h2><p>Market data is temporarily unavailable.</p><button className="app-primary" type="button" onClick={onRetry}>Try again</button></div>
        : baskets.length === 0 ? <div className="state-card" role="status"><span aria-hidden="true">⌕</span><h2>No baskets found</h2><p>Try a different search term or status.</p></div>
        : <div className="market-table terminal-card">
          <div className="market-table-head" aria-hidden="true"><span>Basket</span><span>Price</span><span>24h</span><span>Volume</span><span>Trend</span><span>Expiry</span></div>
          {baskets.map(basket => <Link key={basket.slug} className="market-table-row" to={`/market/${basket.slug}`} aria-label={`${basket.listName}, ${basket.status}, ${basket.priceLabel}, 24 hour change ${formatPercentDelta(basket.changePct)}`}>
            <span className="basket-name"><i aria-hidden="true">{basket.symbol.slice(0, 2)}</i><b>{basket.listName}<small>{basket.symbol}</small></b></span>
            <strong>{basket.priceLabel}</strong>
            <strong className={basket.changePct !== null ? basket.changePct < 0 ? "loss" : "gain" : ""}>{formatPercentDelta(basket.changePct)}</strong>
            <span>{basket.vol}</span><span aria-label="Trend unavailable">—</span><span>{basket.resolvesOn}</span>
          </Link>)}
        </div>}
    </div>
  );
}
