import type { PropsWithChildren } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useDynamicContext } from "@dynamic-labs/sdk-react-core";
import { useTheme } from "next-themes";
import { BarChart3, BriefcaseBusiness, Search, UserRound } from "lucide-react";
import { ThemeIcon } from "./Primitives";
import "./foundation.css";
import "./trading.css";

const routes = [
  { to: "/app", label: "Market", Icon: BarChart3 },
  { to: "/explore", label: "Explore", Icon: Search },
  { to: "/portfolio", label: "Portfolio", Icon: BriefcaseBusiness },
  { to: "/account", label: "Account", Icon: UserRound },
] as const;

export function AppShell({ children }: PropsWithChildren) {
  const { pathname } = useLocation();
  const { user, primaryWallet, setShowAuthFlow } = useDynamicContext();
  const { resolvedTheme, setTheme } = useTheme();
  const theme = resolvedTheme === "dark" ? "dark" : "light";
  const address = primaryWallet?.address;
  const shortAddress = address ? `${address.slice(0, 6)}…${address.slice(-4)}` : null;

  return (
    <div className="xleuth-surface trading-app" data-xleuth-theme={theme}>
      <a className="xleuth-app-skip" href="#xleuth-app-content">Skip to content</a>
      <header className="app-topbar">
        <Link className="app-brand" to="/" aria-label="Back to Xleuth home"><span>X</span><b>Xleuth</b></Link>
        <nav className="desktop-app-nav" aria-label="Trading application">
          {routes.map(route => <NavLink key={route.to} to={route.to} className={pathname === route.to || (route.to === "/app" && pathname.startsWith("/market/")) ? "active" : ""}>{route.label}</NavLink>)}
        </nav>
        <div className="app-top-actions">
          <span className="network-pill"><i /> Testnet</span>
          <details className="app-more">
            <summary>More</summary>
            <nav aria-label="Additional application links">
              <Link to="/how-it-works">How it works</Link>
              <a href="/xleuth-whitepaper.pdf" target="_blank" rel="noopener noreferrer">Whitepaper</a>
              <Link to="/legal-risk-disclosure">Legal &amp; Risk disclosure</Link>
              <Link to="/support">Support</Link>
              <Link to="/privacy">Privacy Policy</Link>
              <Link to="/terms">Terms</Link>
            </nav>
          </details>
          <button className="app-icon-button" type="button" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}><ThemeIcon theme={theme} /></button>
          {user ? (
            <Link className="account-chip" to="/account"><span>{shortAddress ? shortAddress.slice(2, 4).toUpperCase() : "X"}</span><b>{shortAddress ?? "Account"}</b></Link>
          ) : (
            <button className="app-primary sign-in-button" type="button" onClick={() => setShowAuthFlow(true)}>Sign in</button>
          )}
        </div>
      </header>
      <main className="app-main" id="xleuth-app-content">{children}</main>
      <nav className="mobile-tabbar" aria-label="Mobile application navigation">
        {routes.map(route => <NavLink key={route.to} to={route.to} className={pathname === route.to || (route.to === "/app" && pathname.startsWith("/market/")) ? "active" : ""}><route.Icon size={17} aria-hidden="true" /><span>{route.label}</span></NavLink>)}
      </nav>
    </div>
  );
}
