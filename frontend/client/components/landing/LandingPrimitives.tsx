import type { PropsWithChildren, ReactNode } from "react";
import { Link } from "react-router-dom";

export function LandingSection({ id, label, title, children }: PropsWithChildren<{
  id: string; label: string; title: string;
}>) {
  return (
    <section id={id} className="landing-section landing-wrap" aria-labelledby={`${id}-title`}>
      <div className="landing-section-heading">
        <p className="landing-eyebrow">{label}</p>
        <h2 id={`${id}-title`}>{title}</h2>
      </div>
      {children}
    </section>
  );
}

export function LandingAction({ to, children, secondary = false }: {
  to: string; children: ReactNode; secondary?: boolean;
}) {
  return <Link to={to} className={`landing-action${secondary ? " landing-action-secondary" : ""}`}>{children}</Link>;
}

export function LandingHeader() {
  return (
    <header className="landing-header landing-wrap">
      <Link to="/" className="landing-wordmark" translate="no" aria-label="Xleuth home">Xleuth</Link>
      <nav aria-label="Main navigation" className="landing-navigation">
        <a href="#how-it-works">How it works</a>
        <a href="#waitlist">Waitlist</a>
        <LandingAction to="/app">Launch App</LandingAction>
      </nav>
    </header>
  );
}

export function LandingFooter() {
  return (
    <footer className="landing-footer landing-wrap">
      <Link to="/" className="landing-wordmark" translate="no">Xleuth</Link>
      <p>Polygon Amoy testnet · Test assets have no monetary value.</p>
      <nav aria-label="Legal links"><Link to="/privacy">Privacy Policy</Link><Link to="/terms">Terms</Link></nav>
    </footer>
  );
}
