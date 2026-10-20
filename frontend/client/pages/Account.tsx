import { useDynamicContext } from "@dynamic-labs/sdk-react-core";
import { ChevronRight, Copy, LogOut, SquarePen } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { useFaucetClaim, useAccount } from "@/lib/api/hooks";
import { Layout } from "@/components/xleuth/Layout";
import { usePageMeta } from "@/hooks/use-page-meta";

function getInitials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

export default function Account() {
  usePageMeta({ title: 'Account — Xleuth (testnet)', description: 'Manage your connected wallet, display alias and test-USDC faucet on the Polygon Amoy testnet.', path: '/account' });
  const { user, primaryWallet, handleLogOut, setShowAuthFlow } = useDynamicContext();
  const { toast } = useToast();
  const { mutateAsync: claimFaucet, isPending } = useFaucetClaim();
  // Phase 2/4: the backend-derived wallet address is the single source of truth.
  const { data: account } = useAccount();

  const address = account?.wallet_address || primaryWallet?.address;
  const shortAddress = address ? `${address.slice(0, 6)}...${address.slice(-4)}` : null;
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
    <Layout width="md">
      <div className="flex flex-col gap-4 px-4 pt-4 md:px-0 md:pt-0">
        <h1 className="text-lg font-semibold text-neutral-100">Account</h1>

        {user && shortAddress && (
          <div className="flex flex-col gap-6 rounded-2xl border-[0.4px] border-neutral-700 bg-neutral-900 p-4">
            <div className="flex items-center gap-5">
              <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full border-[0.8px] border-primary bg-primary/40">
                <span className="text-sm font-semibold text-[#D3A5D9]">{initials}</span>
              </div>
              <div className="flex flex-1 flex-col gap-1.5">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold tracking-[-0.16px] text-neutral-200">
                    {displayName}
                  </span>
                  <SquarePen className="h-3.5 w-3.5 text-neutral-500" strokeWidth={1.4} />
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-[9px] font-medium text-neutral-500">{shortAddress}</span>
                  <button onClick={handleCopyAddress} aria-label="Copy address">
                    <Copy className="h-3.5 w-3.5 text-neutral-500" strokeWidth={1.4} />
                  </button>
                </div>
              </div>
            </div>

            <div className="flex w-fit items-center gap-1.5 rounded bg-warning/10 px-2 py-1.5">
              <span className="h-2 w-2 rounded-full bg-warning" />
              <span className="text-[10px] font-medium text-warning">
                Polygon Amoy (testnet)
              </span>
            </div>
          </div>
        )}

        <div className="flex flex-col gap-2">
          <div className="flex items-end justify-between gap-4 rounded-2xl border-[0.4px] border-neutral-700 bg-neutral-900 p-4">
            <div className="flex flex-col gap-2">
              <span className="text-[10px] font-medium text-neutral-500">Testnet faucet</span>
              <div className="flex flex-col gap-1">
                <span className="text-xs font-medium tracking-[-0.12px] text-neutral-200">
                  Get test USDC
                </span>
                <span className="text-[9px] font-light text-neutral-500">
                  1,000 USDC every 24 hours
                </span>
              </div>
            </div>
            <button
              onClick={handleClaimFaucet}
              disabled={isPending}
              className="rounded-lg border-[0.4px] border-primary bg-primary/25 px-4 py-2 text-[10px] font-medium text-[#D3A5D9]"
            >
              {isPending ? "Claiming..." : "Claim"}
            </button>
          </div>

          <div className="flex flex-col gap-3 rounded-2xl border-[0.4px] border-neutral-700 bg-neutral-900 p-4">
            <span className="text-[10px] font-medium text-neutral-500">Appearance</span>
            <div className="flex items-end justify-between">
              <span className="text-xs font-medium tracking-[-0.12px] text-neutral-200">
                Theme
              </span>
              <div className="flex items-center gap-3">
                <button className="rounded-lg border-[0.4px] border-primary bg-primary/25 px-4 py-2 text-[10px] font-medium text-[#D3A5D9]">
                  Dark
                </button>
                <button className="rounded-lg border-[0.4px] border-neutral-600 bg-neutral-900 px-4 py-2 text-[10px] font-medium text-neutral-400">
                  Light
                </button>
              </div>
            </div>
          </div>

          {user && (
            <div className="flex flex-col gap-3 rounded-2xl border-[0.4px] border-neutral-700 bg-neutral-900 p-4">
              <span className="text-[10px] font-medium text-neutral-500">Security & Privacy</span>

              <div className="flex items-center justify-between">
                <div className="flex flex-col gap-1">
                  <span className="text-xs font-medium tracking-[-0.12px] text-neutral-200">
                    Wallet key export
                  </span>
                  <span className="text-[9px] font-light text-neutral-500">
                    Export the key for embedded wallet backup
                  </span>
                </div>
                <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-[9px] font-medium text-neutral-500">
                  Coming soon
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-xs font-medium tracking-[-0.12px] text-neutral-200">
                  Session
                </span>
                <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-[9px] font-medium text-neutral-500">
                  Coming soon
                </span>
              </div>
            </div>
          )}

          <div className="flex flex-col gap-3 rounded-2xl border-[0.4px] border-neutral-700 bg-neutral-900 p-4">
            <span className="text-[10px] font-medium text-neutral-500">Support</span>

            <div className="flex items-center justify-between">
              <span className="text-xs font-medium tracking-[-0.12px] text-neutral-200">
                Documentation
              </span>
              <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-[9px] font-medium text-neutral-500">
                Coming soon
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-xs font-medium tracking-[-0.12px] text-neutral-200">
                Discord & Telegram
              </span>
              <ChevronRight className="h-4 w-4 text-neutral-400" strokeWidth={1.4} />
            </div>

            <div className="flex items-center justify-between">
              <span className="text-xs font-medium tracking-[-0.12px] text-neutral-200">
                Report a bug
              </span>
              <ChevronRight className="h-4 w-4 text-neutral-400" strokeWidth={1.4} />
            </div>
          </div>
        </div>

        {user ? (
          <button
            onClick={handleLogOut}
            className="flex items-center gap-2 rounded-xl border-[0.4px] border-neutral-600 p-4 text-destructive"
          >
            <LogOut className="h-4 w-4" strokeWidth={1.6} />
            <span className="text-sm font-medium">Disconnect wallet</span>
          </button>
        ) : (
          <button
            onClick={() => setShowAuthFlow(true)}
            className="flex h-10 w-full items-center justify-center rounded-lg bg-primary px-4 text-base text-white"
          >
            Sign in
          </button>
        )}
      </div>
    </Layout>
  );
}
