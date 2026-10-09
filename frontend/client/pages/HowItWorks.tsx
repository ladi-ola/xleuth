import { InfoPage } from "./InfoPage";
import { usePageMeta } from "@/hooks/use-page-meta";

export default function HowItWorks() {
  usePageMeta({ title: 'How it works — Xleuth (testnet)', description: 'How Xleuth index baskets are built, priced and settled: Polymarket data, VWAP index price and on-chain settlement.', path: '/how-it-works' });
  return (
    <InfoPage
      title="How it works"
      intro="Xleuth helps you explore markets and act on index-based opportunities from one simple interface."
      sections={[
        {
          title: "Explore markets",
          body: "Browse available markets, review the chart, and inspect the resolution criteria before you trade.",
        },
        {
          title: "Choose an action",
          body: "When you are ready, select Buy or Sell and review the order details before confirming.",
        },
        {
          title: "Track your position",
          body: "Your portfolio brings open positions, orders, and trade history together in one place.",
        },
      ]}
    />
  );
}
