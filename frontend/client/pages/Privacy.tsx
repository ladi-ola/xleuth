import { InfoPage } from "./InfoPage";
import { usePageMeta } from "@/hooks/use-page-meta";

export default function Privacy() {
  usePageMeta({ title: "Privacy Policy — Xleuth", description: "Xleuth Privacy Policy.", path: "/privacy" });
  return (
    <InfoPage
      title="Privacy Policy"
      intro="We respect your privacy. Your personal information will be kept confidential, securely stored, and used only for its intended purpose. We will never share your data without your consent, except where legally required."
      sections={[]}
    />
  );
}
