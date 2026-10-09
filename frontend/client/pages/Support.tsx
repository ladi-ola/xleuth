import { InfoPage } from "./InfoPage";

export default function Support() {
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
