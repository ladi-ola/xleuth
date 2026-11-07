import { Copy, LogOut } from "lucide-react";
import { useTheme } from "next-themes";
import { DYNAMIC_ENVIRONMENT_ID } from "@/lib/dynamic";
import "./account-portfolio.css";

export function AccountView({ signedIn, displayName, initials, address, shortAddress, balance, isClaiming, onSignIn, onSignOut, onClaim, onCopyAddress }: {
  signedIn: boolean;
  displayName: string;
  initials: string;
  address: string | null | undefined;
  shortAddress: string | null;
  balance: number | undefined;
  isClaiming: boolean;
  onSignIn: () => void;
  onSignOut: () => void;
  onClaim: () => void;
  onCopyAddress: () => void;
}) {
  const { resolvedTheme, setTheme } = useTheme();

  if (!signedIn) return (
    <div className="app-page centered-page xleuth-account-portfolio">
      <div className="auth-prompt"><span className="account-orb">X</span><h1>Sign in to Xleuth.</h1><p>Sign in to access your testnet trading account.</p><button className="app-primary" type="button" onClick={onSignIn}>Sign in</button><small>Secured by Dynamic · Testnet only</small></div>
    </div>
  );

  return (
    <div className="app-page account-page xleuth-account-portfolio">
      <div className="page-heading"><div><span className="app-kicker">Settings</span><h1>Account</h1><p>Manage your identity and testnet funds.</p></div></div>
      <div className="account-grid">
        <section className="terminal-card profile-card" aria-label="Account profile">
          <div className="profile-top"><span aria-hidden="true">{initials || "X"}</span><div><h2>{displayName}</h2><p>{shortAddress ?? "Wallet address unavailable"}</p></div></div>
          <div className="detail-row"><span>Wallet address</span><b>{shortAddress ?? "—"}{address && <button type="button" aria-label="Copy address" onClick={onCopyAddress}><Copy size={14} /></button>}</b></div>
          <div className="detail-row"><span>Network</span><b><i className="online-dot" /> Polygon Amoy (testnet)</b></div>
          <button className="app-ghost wide" type="button" onClick={onSignOut}><LogOut size={15} /> Sign out</button>
        </section>
        <section className="terminal-card funds-card" aria-label="Testnet funds">
          <span className="app-kicker">Available balance</span>
          <strong>{balance == null || !Number.isFinite(balance) ? "—" : `$${balance.toFixed(2)}`} <small>USDC</small></strong>
          <p>Testnet faucet · 1,000 USDC every 24 hours</p>
          <button className="app-primary wide" type="button" disabled={isClaiming} onClick={onClaim}>{isClaiming ? "Claiming..." : "Claim test tokens"}</button>
          <button className="app-ghost wide" type="button" disabled>Withdraw</button>
        </section>
      </div>
      <section className="terminal-card env-card" aria-label="Dynamic environment"><div><span>Dynamic environment</span><b>{DYNAMIC_ENVIRONMENT_ID}</b></div></section>
      <section className="terminal-card account-settings" aria-label="Appearance and support">
        <div className="detail-row"><span>Appearance · Theme</span><div className="theme-choice"><button type="button" aria-pressed={resolvedTheme === "dark"} onClick={() => setTheme("dark")}>Dark</button><button type="button" aria-pressed={resolvedTheme === "light"} onClick={() => setTheme("light")}>Light</button></div></div>
        <div className="detail-row"><span>Wallet key export</span><small>Coming soon</small></div>
        <div className="detail-row"><span>Session</span><small>Coming soon</small></div>
        <div className="detail-row"><span>Documentation</span><small>Coming soon</small></div>
        <div className="detail-row"><span>Discord &amp; Telegram</span><small>Unavailable</small></div>
        <div className="detail-row"><span>Report a bug</span><small>Unavailable</small></div>
      </section>
    </div>
  );
}
