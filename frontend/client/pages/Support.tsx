import { InfoPage } from "./InfoPage";
import { usePageMeta } from "@/hooks/use-page-meta";

export default function Support() {
  usePageMeta({ title: 'Support — Xleuth (testnet)', description: 'Common questions, contact and bug reports for the Xleuth testnet trading app.', path: '/support' });
  return (
    <InfoPage
      title="Support"
      intro="Need help with Xleuth? Start here and check back as more support resources become available."
      sections={[
        {
          title: "Common questions",
          body: "Guides for markets, orders, wallets, and account access will be added here.",
        },
        {
          title: "Contact us",
          body: "Community and direct support channels are coming soon.",
        },
        {
          title: "Report a bug",
          body: "Please include what happened, what you expected, and any steps needed to reproduce the issue.",
        },
      ]}
    />
  );
}
