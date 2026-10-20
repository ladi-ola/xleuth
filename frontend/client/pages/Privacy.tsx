import { InfoPage } from "./InfoPage";
import { usePageMeta } from "@/hooks/use-page-meta";

export default function Privacy() {
  usePageMeta({
    title: "Privacy Policy — Xleuth",
    description:
      "How Xleuth collects, uses, shares and protects personal information, and the privacy choices available to you.",
    path: "/privacy",
  });

  return (
    <InfoPage
      title="Privacy Policy"
      intro="This Privacy Policy explains how Xleuth collects, uses, shares, and protects information when you access or use our website, applications, and related services (the “Service”). Xleuth is currently provided as a testnet product, and test assets have no monetary value. By using the Service, you acknowledge the practices described in this Policy. Last updated: October 20, 2026."
      sections={[
        {
          title: "Who we are",
          body: "Xleuth operates the Service. For privacy questions or requests, contact us at privacy@xleuth.xyz or through the Support page.",
        },
        {
          title: "Information we collect",
          body: "We collect information you provide directly, such as your wallet address, an optional display name or alias, and any messages you send to support. When you use the Service, we also collect information about your activity, including orders, positions, balances, transactions, faucet claims, and other interactions with the Service, as well as technical information such as IP address, browser type, device information, pages visited, and referral source. We do not require your name, email address, password, or payment card details to use the core Service. If you contact us, we receive whatever information you choose to include.",
        },
        {
          title: "Blockchain and public data",
          body: "Transactions involving the Service are recorded on a public test blockchain. Wallet addresses, balances, positions, orders, transaction hashes, and related data may be publicly visible and permanent. We cannot edit or delete information recorded on a blockchain. Please do not use a wallet address that you need to keep private.",
        },
        {
          title: "How we use information",
          body: "We use information to provide, operate, and maintain the Service; authenticate your wallet and maintain your session; process orders, positions, balances, and transactions; enforce faucet limits; detect, prevent, and address fraud, abuse, and security issues; comply with applicable law and enforce our terms; communicate with you about the Service; and understand and improve how the Service works.",
        },
        {
          title: "Legal bases for processing",
          body: "Where required by applicable law, we process personal information on the basis of performing our contract with you, our legitimate interests in operating and securing the Service, compliance with legal obligations, or your consent. You may withdraw consent at any time where processing is based on consent, without affecting processing that occurred before withdrawal.",
        },
        {
          title: "How we share information",
          body: "We do not sell personal information. We may share information with service providers that help us operate the Service, such as hosting, wallet authentication, blockchain infrastructure, market data, analytics, and customer support providers, subject to appropriate confidentiality and data protection obligations. We may also share information with professional advisers, authorities or other parties when required by law or necessary to protect rights and safety, and with a successor or acquirer in connection with a business transaction. We may share information with your consent or at your direction. Information recorded on a public blockchain is inherently public.",
        },
        {
          title: "Cookies and similar technologies",
          body: "We use strictly necessary cookies and local storage to keep you signed in, maintain your wallet connection, remember interface preferences, and protect the Service. If we enable analytics, it is limited to aggregated usage information, is designed not to identify you, and does not use advertising cookies. We honor Do Not Track and Global Privacy Control where supported. You can control cookies through your browser settings, but disabling strictly necessary storage may prevent parts of the Service from working.",
        },
        {
          title: "Data retention",
          body: "We retain information for as long as necessary to provide the Service, meet legal, security, and accounting requirements, resolve disputes, and enforce our agreements. Because the Service operates in a testnet environment, some or all app-side data may be reset or deleted without individual notice. Backup copies may be retained for a limited period. Information recorded on a public blockchain may be retained permanently by the network and cannot be deleted by us.",
        },
        {
          title: "How we protect information",
          body: "We use reasonable technical and organizational measures designed to protect information against unauthorized access, loss, misuse, and alteration. However, no method of transmission or storage is completely secure, and we cannot guarantee absolute security. You are responsible for protecting your wallet, credentials, and devices.",
        },
        {
          title: "Your rights and choices",
          body: "Depending on where you live, you may have the right to access, correct, delete, restrict, or object to the processing of your personal information, request portability, withdraw consent, or lodge a complaint with a supervisory authority. To exercise these rights, contact us at privacy@xleuth.xyz. We may need to verify that you control the relevant wallet before acting on a request. Information recorded on a public blockchain cannot be changed or deleted, and we may retain certain information where required by law.",
        },
        {
          title: "International transfers",
          body: "Information may be processed in countries other than the one in which you live. Where required by applicable law, we use appropriate safeguards for such transfers.",
        },
        {
          title: "Children",
          body: "The Service is intended for adults aged 18 and over and is not directed to children. We do not knowingly collect personal information from anyone under 18. If we learn that we have collected such information, we will take reasonable steps to delete it.",
        },
        {
          title: "Changes to this Policy",
          body: "We may update this Privacy Policy from time to time. When we do, we will revise the “Last updated” date above. If a change is material, we will provide additional notice where appropriate. Your continued use of the Service after an update means you acknowledge the revised Policy.",
        },
        {
          title: "Contact us",
          body: "If you have questions about this Privacy Policy or our privacy practices, contact us at privacy@xleuth.xyz or through the Support page.",
        },
      ]}
    />
  );
}
