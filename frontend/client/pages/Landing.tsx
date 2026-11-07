import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, ThemeIcon } from "@/components/figma/Primitives";
import { FigmaWaitlistForm } from "@/components/figma/FigmaWaitlistForm";
import { backendApi } from "@/lib/api/backend";
import type { BasketInfo, BasketPriceResponseWithChange, PricePoint } from "@/lib/api/schemas";
import { formatPercentDelta } from "@/lib/format";
import { usePageMeta } from "@/hooks/use-page-meta";
import "@/components/figma/foundation.css";
import "./figma-landing.css";

type Theme = "light" | "dark";

const steps = [
  ["01", "Choose a basket", "Take a view on a curated group of related prediction markets in one position."],
  ["02", "Set your exposure", "Choose long or short, add collateral, and set leverage with clear risk visibility."],
  ["03", "Trade the index", "Track the basket as its markets move."],
] as const;

const features = [
  { number: "01", title: "Index baskets", copy: "Trade a broader thesis instead of managing isolated market positions.", visual: "basket" },
  { number: "02", title: "Flexible leverage", copy: "Express conviction with adjustable exposure and transparent position details.", visual: "leverage" },
  { number: "04", title: "Cash-settled", copy: "Positions settle in stablecoins—no individual outcome tokens to manage.", visual: "settle" },
] as const;

function useLivePreview() {
  const [data, setData] = useState<{
    basket: BasketInfo;
    price: BasketPriceResponseWithChange | null;
    history: PricePoint[];
  } | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const response = await backendApi.getBaskets();
        const basket = response.baskets.find(item => item.is_tradeable) ?? response.baskets[0];
        if (!basket) {
          if (active) setError(true);
          return;
        }
        if (active) setData({ basket, price: null, history: [] });
        const [price, history] = await Promise.allSettled([
          backendApi.getBasketPrice(basket.basket_name),
          backendApi.getBasketHistory(basket.basket_name, { limit: 80 }),
        ]);
        if (active) setData({
          basket,
          price: price.status === "fulfilled" ? price.value : null,
          history: history.status === "fulfilled" ? history.value.prices : [],
        });
      } catch {
        if (active) setError(true);
      }
    }
    void load();
    return () => { active = false; };
  }, []);
  return { data, error };
}

function LivePreview() {
  const { data, error } = useLivePreview();
  const price = data?.price?.scaled_price ?? data?.basket.index_price_scaled;
  const points = data?.history.map(item => item.scaled_price).filter((value): value is number => value !== null) ?? [];
  const minimum = points.length ? Math.min(...points) : 0;
  const maximum = points.length ? Math.max(...points) : 1;
  const line = points.map((value, index) => {
    const x = points.length === 1 ? 0 : (index / (points.length - 1)) * 720;
    const y = 220 - (value - minimum) / Math.max(maximum - minimum, 0.001) * 190;
    return `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`;
  }).join(" ");

  return (
    <div className="product-shell" role="group" aria-label="Live Xleuth market preview">
      <div className="product-topbar">
        <div className="product-brand"><span className="x-mark">X</span><span>Xleuth</span></div>
        <div className="product-tabs"><span className="active">Trade</span><span>Portfolio</span></div>
        <div className="wallet-pill">Testnet</div>
      </div>
      <div className="product-body">
        <div className="chart-panel">
          <div className="asset-heading">
            <div><span className="eyebrow">BASKET / 24H</span><strong className="preview-market-name">{data?.basket.basket_name ?? "Markets"}</strong></div>
            <div className="price-block">
              <strong>{typeof price === "number" ? price.toFixed(3) : "—"}</strong>
              <span>{formatPercentDelta(data?.price?.change_24h_pct)}</span>
            </div>
          </div>
          <div className="chart-wrap">
            {line ? (
              <svg viewBox="0 0 720 260" preserveAspectRatio="none" role="img" aria-label={`Recent price history for ${data?.basket.basket_name}`}>
                <defs><linearGradient id="liveChartFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="var(--signal)" stopOpacity=".28" /><stop offset="100%" stopColor="var(--signal)" stopOpacity="0" /></linearGradient></defs>
                <g className="grid-lines"><path d="M0 22H720M0 84H720M0 146H720M0 208H720" /></g>
                <path className="area" fill="url(#liveChartFill)" d={`${line} L720 260 L0 260 Z`} />
                <path className="line" d={line} />
              </svg>
            ) : <p className="preview-empty" role="status">{error ? "Market data unavailable" : data ? "No price history available" : "Loading markets…"}</p>}
          </div>
          <div className="basket-row"><span>IN THIS BASKET</span><p>{data ? `${data.basket.total_constituents} markets` : "—"}</p></div>
        </div>
        <div className="order-panel">
          <div className="order-heading"><strong>Place order</strong><span>Testnet</span></div>
          <div className="side-toggle" aria-hidden="true"><button type="button" className="selected" disabled>Long</button><button type="button" disabled>Short</button></div>
          <p className="order-label">Collateral <span>Sign in to view balance</span></p>
          <div className="amount-input"><span>$</span><strong>—</strong><i>USDC</i></div>
          <p className="order-label">Leverage</p>
          <div className="order-summary"><p><span>Entry price</span><b>{typeof price === "number" ? price.toFixed(3) : "—"}</b></p><p><span>Position size</span><b>—</b></p><p><span>Est. fee</span><b>—</b></p></div>
          <Link className="trade-button" to={data?.basket.slug ? `/market/${data.basket.slug}` : "/app"}>Launch App <ArrowUpRight /></Link>
        </div>
      </div>
    </div>
  );
}

function FeatureVisual({ visual }: { visual: typeof features[number]["visual"] }) {
  if (visual === "basket") return <div className="basket-visual" aria-hidden="true"><span /><span /><span /><i /></div>;
  if (visual === "leverage") return <div className="leverage-visual" aria-hidden="true">{[1, 2, 3, 4, 5].map(n => <b key={n} className={n === 3 ? "on" : ""}>{n}×</b>)}</div>;
  return <div className="settle-visual" aria-hidden="true"><span>MARKETS</span><i>→</i><strong>USDC</strong></div>;
}

export default function Landing() {
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem("xleuth-landing-theme");
    return saved === "light" || saved === "dark" ? saved : window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => { localStorage.setItem("xleuth-landing-theme", theme); }, [theme]);
  usePageMeta({ title: "Xleuth — Trade the signal, not the noise", description: "Leveraged index baskets for prediction markets. One position, a wider view.", path: "/", image: "/favicon.png" });

  return (
    <div className="figma-surface site" data-figma-theme={theme}>
      <a className="figma-skip" href="#main-content">Skip to content</a>
      <header className="nav-wrap">
        <nav className="nav container" aria-label="Main navigation">
          <Link to="/" className="wordmark" aria-label="Xleuth home">Xleuth<span>.</span></Link>
          <div className={`nav-links ${menuOpen ? "open" : ""}`} id="landing-navigation">
            <a href="#how" onClick={() => setMenuOpen(false)}>How it works</a>
            <a href="#features" onClick={() => setMenuOpen(false)}>Features</a>
            <a href="#waitlist" onClick={() => setMenuOpen(false)}>Waitlist</a>
          </div>
          <div className="nav-actions">
            <button className="icon-button theme-toggle" type="button" aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}><ThemeIcon theme={theme} /></button>
            <Link className="button button-small button-dark" to="/app">Launch App <ArrowUpRight size={14} /></Link>
            <button className="icon-button menu-toggle" type="button" aria-label="Toggle navigation menu" aria-controls="landing-navigation" aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}><span /><span /></button>
          </div>
        </nav>
      </header>

      <main id="main-content">
        <section className="hero container">
          <div className="ambient ambient-one" />
          <div className="hero-copy">
            <div className="status-chip"><span /> Live on testnet</div>
            <h1>Trade the signal,<br /><em>not the noise.</em></h1>
            <p>Leveraged index baskets for prediction markets. One position, a wider view.</p>
            <div className="hero-actions"><Link className="button button-primary" to="/app">Launch App <ArrowUpRight /></Link><a className="button button-secondary" href="#waitlist">Join waitlist</a></div>
          </div>
          <div className="preview-stage"><LivePreview /></div>
        </section>

        <section className="section how-section container" id="how">
          <div className="section-heading split-heading"><div><span className="kicker">How it works</span><h2>From thesis<br />to trade.</h2></div><p>Xleuth packages related prediction markets into a single, tradable index—so you can focus on the idea, not the plumbing.</p></div>
          <div className="steps-grid">{steps.map(([number, title, copy], index) => <article className="step-card" key={number}><div className="step-top"><span>{number}</span>{index < 2 && <i />}</div><div className={`step-symbol symbol-${index + 1}`} aria-hidden="true"><span>{index === 0 ? "＋" : index === 1 ? "×" : "↗"}</span></div><h3>{title}</h3><p>{copy}</p></article>)}</div>
        </section>

        <section className="section feature-section" id="features">
          <div className="container"><div className="section-heading centered-heading"><span className="kicker">Built for a wider view</span><h2>One platform.<br /><em>More ways to trade.</em></h2></div><div className="feature-grid">{features.map(feature => <article className="feature-card" key={feature.number}><div className="feature-meta"><span>{feature.number}</span><i /></div><div className="feature-visual"><FeatureVisual visual={feature.visual} /></div><h3>{feature.title}</h3><p>{feature.copy}</p></article>)}</div></div>
        </section>

        <section className="section statement-section container"><span className="kicker">Trade the whole story</span><p className="statement">Markets move together.<br /><em>Your positions should, too.</em></p><div className="orbit-graphic" aria-hidden="true"><div className="orbit orbit-a"><i /><i /><i /><i /></div><div className="orbit orbit-b"><i /><i /><i /></div><div className="orbit-center">X</div></div></section>

        <section className="section waitlist-section" id="waitlist"><div className="ambient ambient-two" /><div className="container waitlist-inner"><div className="waitlist-copy"><span className="kicker">Mainnet access</span><h2>Get early access<br />to <em>mainnet.</em></h2><p>Join the list for product updates and first access when Xleuth moves beyond testnet.</p></div><div className="form-card"><FigmaWaitlistForm /></div></div></section>
      </main>

      <footer><div className="container footer-top"><div><Link to="/" className="wordmark footer-wordmark">Xleuth<span>.</span></Link><p>A wider view of prediction markets.</p></div><div className="footer-links"><a href="#how">How it works</a><a href="#features">Features</a><a href="#waitlist">Waitlist</a></div><Link className="button button-light" to="/app">Launch App <ArrowUpRight /></Link></div><div className="container footer-bottom"><p>Xleuth is currently on testnet. Leveraged trading involves significant risk and may not be suitable for everyone.</p><span>© {new Date().getFullYear()} Xleuth</span></div></footer>
    </div>
  );
}
