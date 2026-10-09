import { InfoPage } from "./InfoPage";
import { usePageMeta } from "@/hooks/use-page-meta";

export default function Privacy() {
  usePageMeta({ title: 'Privacy Policy — Xleuth (testnet)', description: 'What Xleuth collects, why, and your rights. Wallet addresses, session handling, cookies and on-chain data.', path: '/privacy' });
  return (
    <InfoPage
      title="Privacy Policy"
      intro="Plain-English summary of what Xleuth collects and why. The full version lives in docs/privacy-policy.md in the repo. Operator contact details will appear here once confirmed."
      sections={[
        {
          title: "Testnet notice",
          body: "Xleuth runs on the Polygon Amoy testnet with test USDC that has no monetary value. Testnet data may be reset at any time.",
        },
        {
          title: "What we collect",
          body: "Your wallet address and display alias; balances, positions, orders and transaction history tied to that address; the faucet claim timestamp; Dynamic sign-in tokens (verified, then exchanged for a 60-minute app session kept in memory, never in cookies or localStorage).",
        },
        {
          title: "What is public forever",
          body: "Anything written to the Polygon Amoy chain — wallet address, balances, positions, prices, transaction hashes — is public and permanent. It cannot be deleted, including by us.",
        },
        {
          title: "Third parties",
          body: "Dynamic (sign-in), Google Fonts (typeface), Builder.io (logo image host), Alchemy (RPC endpoint), Polygon Amoy public RPC, and Polymarket public market-data APIs. Each sees your IP address when your device contacts it.",
        },
        {
          title: "Cookies and storage",
          body: "Strictly necessary only: sign-in session in memory, wallet connection state via Dynamic, and one sidebar-collapse preference cookie (7 days). Cookieless usage analytics only if the operator enables it — nothing fires before that, and Do Not Track / Global Privacy Control are respected.",
        },
        {
          title: "Retention and rights",
          body: "App-database records persist until a testnet reset; contact the operator to remove your alias or app-side records. On-chain records cannot be removed. Service is 18+ only.",
        },
      ]}
    />
  );
}
