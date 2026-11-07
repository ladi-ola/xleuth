import { useDynamicContext } from "@dynamic-labs/sdk-react-core";
import { useToast } from "@/hooks/use-toast";
import { useFaucetClaim, useAccount } from "@/lib/api/hooks";
import { AppShell } from "@/components/xleuth/AppShell";
import { AccountView } from "@/components/xleuth/AccountView";
import { usePageMeta } from "@/hooks/use-page-meta";

function getInitials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

export default function Account() {
  usePageMeta({
    title: "Account — Xleuth (testnet)",
    description:
      "Manage your connected wallet, display alias and test-USDC faucet on the Polygon Amoy testnet.",
    path: "/account",
  });
  const { user, primaryWallet, handleLogOut, setShowAuthFlow } =
    useDynamicContext();
  const { toast } = useToast();
  const { mutateAsync: claimFaucet, isPending } = useFaucetClaim();
  // Phase 2/4: the backend-derived wallet address is the single source of truth.
  const { data: account } = useAccount();

  const address = account?.wallet_address || primaryWallet?.address;
  const shortAddress = address
    ? `${address.slice(0, 6)}...${address.slice(-4)}`
    : null;
  const displayName = account?.alias || user?.alias || shortAddress || "Wallet";
  const initials = getInitials(displayName);

  const handleCopyAddress = () => {
    if (!address) return;
    navigator.clipboard.writeText(address);
    toast({ title: "Address copied" });
  };

  const handleClaimFaucet = async () => {
    if (!user) return setShowAuthFlow(true);
    // useFaucetClaim surfaces success/error/cooldown toasts itself.
    try {
      await claimFaucet();
    } catch {
      // Error already reported by the mutation hook.
    }
  };

  return (
    <AppShell>
      <AccountView
        signedIn={!!user}
        displayName={displayName}
        initials={initials}
        address={address}
        shortAddress={shortAddress}
        balance={account?.balance}
        isClaiming={isPending}
        onSignIn={() => setShowAuthFlow(true)}
        onSignOut={handleLogOut}
        onClaim={handleClaimFaucet}
        onCopyAddress={handleCopyAddress}
      />
    </AppShell>
  );
}
