import { InfoPage } from "./InfoPage";
import { usePageMeta } from "@/hooks/use-page-meta";

export default function LegalRiskDisclosure() {
  usePageMeta({ title: 'Legal and risk disclosure — Xleuth (testnet)', description: 'Key risks of using Xleuth: experimental product, market risk and Amoy testnet assets with no monetary value.', path: '/legal-risk-disclosure' });
  return (
    <InfoPage
      title="Legal & Risk disclosure"
      intro="Please review the key risks before using Xleuth. This brief summary will be expanded with the full disclosure later."
      sections={[
        {
          title: "Experimental product",
          body: "Xleuth is under active development. Features, markets, and terms may change as the product evolves.",
        },
        {
          title: "Market risk",
          body: "Trading involves risk, including the possible loss of funds. Past performance does not guarantee future results.",
        },
        {
          title: "Testnet only",
          body: "Polygon Amoy testnet assets are not real funds and have no expected monetary value.",
        },
      ]}
    />
  );
}
