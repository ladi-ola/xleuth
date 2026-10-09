import { InfoPage } from "./InfoPage";
import { usePageMeta } from "@/hooks/use-page-meta";

export default function Terms() {
  usePageMeta({ title: 'Terms and Conditions — Xleuth (testnet)', description: 'Testnet-only terms for Xleuth: no monetary value, no advice, eligibility, acceptable use and liability.', path: '/terms' });
  return (
    <InfoPage
      title="Terms and Conditions"
      intro="Plain-English summary. The full version lives in docs/terms.md in the repo. This is not legal advice."
      sections={[
        {
          title: "Testnet only, no guarantees",
          body: "Xleuth is an experimental testnet service. Test USDC has no monetary value. The service may be reset, paused or modified at any time, and test funds can be lost without recourse.",
        },
        {
          title: "Not financial advice",
          body: "Nothing here is financial, investment or legal advice. Leveraged index products can lose everything put into them; do not treat testnet behavior as predictive of anything.",
        },
        {
          title: "Third-party data",
          body: "Index data comes from Polymarket/UMA via public APIs and may be wrong, delayed or disputed. Oracle prices are pushed by a single operator key and settle positions on-chain as described in How it works.",
        },
        {
          title: "Eligibility and your keys",
          body: "18+ only. Access may be restricted in some jurisdictions. You are responsible for your own wallet and keys — we never take custody of them.",
        },
        {
          title: "Acceptable use",
          body: "No abuse, exploitation, market manipulation, or automated attacks outside an agreed bug-bounty process. We may suspend access for violations.",
        },
        {
          title: "Liability and changes",
          body: "Service provided as-is, without warranties, to the maximum extent allowed by applicable law. Terms may change; material changes will be noted here.",
        },
      ]}
    />
  );
}
