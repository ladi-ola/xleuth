import { InfoPage } from "./InfoPage";

export default function LegalRiskDisclosure() {
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
