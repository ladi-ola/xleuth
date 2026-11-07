import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Link } from "react-router-dom";
import type { Basket, OrderBookRow } from "@/lib/market-data";
import type { BasketInfo } from "@/lib/api/schemas";
import { formatPercentDelta } from "@/lib/format";
import { useIsTablet } from "@/hooks/use-media-query";
import { PriceChart } from "@/components/xleuth/PriceChart";
import { OrderBook } from "@/components/xleuth/OrderBook";
import { IndexDetailsCard } from "@/components/xleuth/IndexDetailsCard";

type Panel = "chart" | "order-book" | "trade";

/** Presentation only: the page continues to own public queries and orders. */
export function FigmaMarketsView({ basket, basketName, basketOptions, candles, orderBook, constituents, signedIn, onTrade }: {
  basket: Basket;
  basketName: string;
  basketOptions: BasketInfo[];
  candles?: { time: number; open: number; high: number; low: number; close: number }[];
  orderBook?: { buys: OrderBookRow[]; sells: OrderBookRow[] };
  constituents?: string[];
  signedIn: boolean;
  onTrade: (side: "buy" | "sell") => void;
}) {
  const [panel, setPanel] = useState<Panel>("chart");
  const [showOrderBook, setShowOrderBook] = useState(true);
  const isTablet = useIsTablet();
  const marketPath = (item: BasketInfo) => `/market/${item.slug ?? item.basket_name.toLowerCase().replace(/_/g, "-")}`;

  return (
    <div className="market-screen">
      <section className="market-strip terminal-card" aria-label="Selected market">
        <Link className="basket-select" to="/explore"><span className="basket-badge">X</span><span><b>{basket.listName}</b><small>{basket.symbol}</small></span><span aria-hidden="true">⌄</span></Link>
        <div className="market-stat price-stat"><span>Index price</span><strong>{basket.priceLabel}</strong></div>
        <div className="market-stat"><span>24h change</span><strong className={basket.changePct !== null && basket.changePct < 0 ? "loss" : "gain"}>{formatPercentDelta(basket.changePct)}</strong></div>
        <div className="market-stat"><span>Expiry</span><strong>{basket.resolvesOn}</strong></div>
        <div className="live-market"><i /> {basket.tradeable ? "Market live" : basket.status}</div>
      </section>

      <div className="mobile-market-tabs" role="group" aria-label="Market panel">
        {(["chart", "order-book", "trade"] as Panel[]).map(item => <button type="button" key={item} className={panel === item ? "active" : ""} aria-pressed={panel === item} onClick={() => setPanel(item)}>{item === "order-book" ? "Orderbook" : item === "trade" ? "Trade" : "Chart"}</button>)}
      </div>

      <div className="terminal-grid">
        <section className={`terminal-card chart-card mobile-${panel === "chart" ? "show" : "hide"}`} aria-label="Price chart">
          <div className="panel-title"><strong>Price chart</strong><span>{basket.symbol}</span></div>
          <div className="figma-chart">{(isTablet || panel === "chart") && <PriceChart candles={candles} terminalPalette />}</div>
          <div className="market-chart-label"><b>{basket.symbol}</b><span>{basket.updatedLabel}</span></div>
        </section>

        <aside id="desktop-order-book" className={`terminal-card figma-orderbook mobile-${panel === "order-book" ? "show" : "hide"}`} aria-label="Order book">
          <div className="panel-title"><strong>Orderbook</strong><button type="button" className="figma-book-toggle" aria-controls="market-order-book" aria-pressed={showOrderBook} onClick={() => setShowOrderBook(value => !value)}>{showOrderBook ? <EyeOff size={14} /> : <Eye size={14} />}{showOrderBook ? "Hide" : "Show"}</button></div>
          {showOrderBook && <div id="market-order-book"><OrderBook priceLabel={basket.priceLabel} buys={orderBook?.buys} sells={orderBook?.sells} /></div>}
        </aside>

        <section className={`terminal-card figma-trade-card mobile-${panel === "trade" ? "show" : "hide"}`} aria-label="Place an order">
          <div className="panel-title"><strong>Place order</strong><span>Testnet</span></div>
          <p>{signedIn ? "Choose a side to open the order ticket." : "Sign in to trade on testnet."}</p>
          <div className="trade-options"><button type="button" onClick={() => onTrade("buy")}>Buy</button><button type="button" className="sell" onClick={() => onTrade("sell")}>Sell</button></div>
        </section>
      </div>

      <div className="market-details"><IndexDetailsCard basket={basket} constituents={constituents} /></div>
      <section className="market-list terminal-card" aria-label="Markets"><h2>Markets</h2><div className="market-list-items">{basketOptions.map(item => <Link key={item.basket_name} to={marketPath(item)} aria-current={item.basket_name === basketName ? "page" : undefined}>{item.basket_name}</Link>)}</div></section>
      <div className="mobile-trade-actions"><button type="button" onClick={() => onTrade("buy")}>Buy</button><button type="button" className="sell" onClick={() => onTrade("sell")}>Sell</button></div>
    </div>
  );
}
