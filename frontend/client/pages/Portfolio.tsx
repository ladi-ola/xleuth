import { useState } from "react";
import { useDynamicContext } from "@dynamic-labs/sdk-react-core";
import { track } from "@/lib/analytics";
import {
  useAccount,
  useCancelOrder,
  useFaucetClaim,
  useVaultDeposit,
  usePortfolioSummary,
  usePositions,
  useOpenOrders,
  useOrderHistory,
  useTransactions,
} from "@/lib/api/hooks";
import {
  adaptPortfolioSummary,
  adaptPosition,
  adaptOpenOrder,
  adaptHistoryOrder,
  adaptTransaction,
} from "@/lib/api/adapters";
import { FigmaAppShell } from "@/components/figma/FigmaAppShell";
import { FigmaPortfolioView, type PortfolioTab } from "@/components/figma/FigmaPortfolioView";
import { SignInSheet } from "@/components/xleuth/SignInSheet";
import { useToast } from "@/hooks/use-toast";
import { getBasket } from "@/lib/market-data";
import { usePageMeta } from "@/hooks/use-page-meta";
import type { Position, OpenOrder, HistoryOrder } from "@/lib/portfolio-data";

export default function Portfolio() {
  usePageMeta({
    title: "Portfolio — Xleuth (testnet)",
    description:
      "Track test-USDC balances, open positions, orders and trade history on the Polygon Amoy testnet.",
    path: "/portfolio",
  });
  const [tab, setTab] = useState<PortfolioTab>("position");
  const [showSignIn, setShowSignIn] = useState(false);
  const { user } = useDynamicContext();
  const { toast } = useToast();
  const { mutateAsync: claimFaucet, isPending: isClaiming } = useFaucetClaim();
  const { mutateAsync: depositToVault, isPending: isDepositing } = useVaultDeposit();
  const { mutate: cancelOrder, isPending: isCancelling } = useCancelOrder();

  // Phase 4: authenticated reads. The hooks poll while the screen is mounted
  // (see queryOptions.authenticated), pause while the tab is hidden, refetch
  // on focus/reconnect and are invalidated after any order mutation or claim.
  // useAccount warms the wallet_address cache the faucet claim sends as recipient.
  useAccount();
  const { data: summaryData } = usePortfolioSummary();
  const { data: positionsData } = usePositions();
  const { data: openOrdersData } = useOpenOrders();
  const { data: historyData } = useOrderHistory();
  const { data: transactionsData } = useTransactions();

  const summary = summaryData ? adaptPortfolioSummary(summaryData) : null;
  const positions: Position[] =
    positionsData?.positions.map(adaptPosition) ?? [];
  const openOrders: OpenOrder[] =
    openOrdersData?.orders.map(adaptOpenOrder) ?? [];
  const tradeHistory: HistoryOrder[] =
    historyData?.orders.map(adaptHistoryOrder) ?? [];
  const transferHistory: HistoryOrder[] = (transactionsData?.transactions ?? [])
    .map(adaptTransaction)
    .filter((entry) => entry.kind === "transfer");
  const historyOrders: HistoryOrder[] = [...tradeHistory, ...transferHistory];

  const handleClaim = async () => {
    if (!user) return setShowSignIn(true);
    // useFaucetClaim surfaces success/error/cooldown toasts itself.
    try {
      track("faucet_claim_submitted");
      await claimFaucet();
    } catch {
      // Error already reported by the mutation hook.
    }
  };

  const handleDeposit = async () => {
    if (!user) return setShowSignIn(true);
    // useVaultDeposit re-reads the wallet balance and signs approve + deposit
    // with the connected wallet. It surfaces success/error toasts itself.
    try {
      track("deposit_submitted");
      await depositToVault(undefined);
    } catch {
      // Error already reported by the mutation hook.
    }
  };

  const handleWithdraw = () => {
    // Withdraw is explicitly out of scope for this batch.
    toast({
      title: "Withdraw coming soon",
      description: "This flow isn't wired up yet.",
    });
  };

  return (
    <FigmaAppShell>
      <FigmaPortfolioView
        tab={tab}
        onTabChange={setTab}
        summary={summary}
        positions={positions}
        rawPositions={positionsData?.positions ?? []}
        openOrders={openOrders}
        historyOrders={historyOrders}
        isCancelling={isCancelling}
        onCancel={(id) => cancelOrder(id)}
        isClaiming={isClaiming}
        isDepositing={isDepositing}
        onClaim={handleClaim}
        onDeposit={handleDeposit}
        onWithdraw={handleWithdraw}
      />
      {showSignIn && (
        <SignInSheet
          basket={getBasket(undefined)}
          onClose={() => setShowSignIn(false)}
        />
      )}
    </FigmaAppShell>
  );
}
