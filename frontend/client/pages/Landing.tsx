import { LandingAction, LandingFooter, LandingHeader, LandingSection } from "@/components/landing/LandingPrimitives";
import { WaitlistForm } from "@/components/landing/WaitlistForm";
import { usePageMeta } from "@/hooks/use-page-meta";
import "./landing.css";

export default function Landing() {
  usePageMeta({
    title: "Xleuth — prediction-market index futures on testnet",
    description: "Explore dated index futures over prediction-market baskets on Polygon Amoy testnet. Trade with test USDC; no real funds.",
    path: "/",
    image: "/favicon.png",
  });

  return (
    <div className="landing">
      <a className="landing-skip" href="#main-content">Skip to content</a>
      <LandingHeader />
      <main id="main-content">
        <section className="landing-hero landing-wrap" aria-labelledby="landing-title">
          <div className="landing-hero-copy">
            <p className="landing-eyebrow">POLYGON AMOY · TESTNET ONLY</p>
            <h1 id="landing-title">Prediction markets, in an index.</h1>
            <p className="landing-lead">Trade dated futures on baskets of prediction markets. One index brings multiple market outcomes into view, with test USDC collateral and no real funds.</p>
            <div className="landing-hero-actions"><LandingAction to="/app">Launch App</LandingAction><a href="#how-it-works" className="landing-text-link">See how it works</a></div>
          </div>
          <div className="landing-index" role="group" aria-label="Markets combined into a single index">
            <div className="landing-index-heading"><span>BASKET</span><span>INDEX</span></div>
            <div className="landing-index-row"><span>Market outcomes</span><span>Combined</span></div>
            <div className="landing-index-flow" aria-hidden="true"><span /><span /><span /><span /></div>
            <div className="landing-index-result"><span>One basket</span><strong>One index</strong></div>
            <p>Multiple prediction markets. One dated future.</p>
          </div>
        </section>

        <LandingSection id="how-it-works" label="THE STRUCTURE" title="A basket with a defined end.">
          <div className="landing-feature-grid">
            <article><span className="landing-feature-label">01 / BASKET</span><h3>Markets grouped by theme</h3><p>Each basket tracks a selection of Polymarket markets, combined into a single index.</p></article>
            <article><span className="landing-feature-label">02 / FUTURE</span><h3>A dated position</h3><p>Trade a cash-settled index future with an expiry, rather than a perpetual contract.</p></article>
            <article><span className="landing-feature-label">03 / TESTNET</span><h3>Try it on Amoy</h3><p>Orders match off-chain and settle on Polygon Amoy. Collateral is test USDC, not real funds.</p></article>
          </div>
        </LandingSection>

        <LandingSection id="trade" label="THE APP" title="See the basket. Trade the index.">
          <div className="landing-trade-row">
            <p>Explore basket constituents, follow index prices, view the order book and manage positions in one place. Trading is currently available only on testnet.</p>
            <LandingAction to="/app">Launch App</LandingAction>
          </div>
        </LandingSection>

        <LandingSection id="waitlist" label="STAY IN THE LOOP" title="Join the waitlist.">
          <div className="landing-waitlist-grid">
            <p>Interested in what comes next for Xleuth? Leave your name and email to hear from us. The app is on testnet today.</p>
            <WaitlistForm />
          </div>
        </LandingSection>
      </main>
      <LandingFooter />
    </div>
  );
}
