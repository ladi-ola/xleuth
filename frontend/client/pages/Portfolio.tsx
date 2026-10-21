import { useState } from "react";
import { Download, Upload } from "lucide-react";
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
import { Layout } from "@/components/xleuth/Layout";
import { PositionCard } from "@/components/xleuth/PositionCard";
import { OpenOrderCard } from "@/components/xleuth/OpenOrderCard";
import { HistoryCard } from "@/components/xleuth/HistoryCard";
import { EmptyState } from "@/components/xleuth/EmptyState";
import { SignInSheet } from "@/components/xleuth/SignInSheet";
import { SegmentedControl } from "@/components/xleuth/SegmentedControl";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { getBasket } from "@/lib/market-data";
import { usePageMeta } from "@/hooks/use-page-meta";
import {
  pnlPeriods,
  type PnlPeriod,
  type Position,
  type OpenOrder,
  type HistoryOrder,
} from "@/lib/portfolio-data";

type Tab = "position" | "open" | "history";

// Neutral placeholder used while the live summary is loading. The portfolio
// card only renders for signed-in users, so these zeros are never presented
// as a real balance.
const EMPTY_SUMMARY = {
  totalBalance: 0,
  unrealizedPnl: 0,
  freeMargin: 0,
  usedMargin: 0,
  profitLoss: 0,
  walletBalance: 0,
};

export default function Portfolio() {
  usePageMeta({
    title: "Portfolio — Xleuth (testnet)",
    description:
      "Track test-USDC balances, open positions, orders and trade history on the Polygon Amoy testnet.",
    path: "/portfolio",
  });
  const [tab, setTab] = useState<Tab>("position");
  const [period, setPeriod] = useState<PnlPeriod>("YTD");
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

  const summary = summaryData
    ? adaptPortfolioSummary(summaryData)
    : EMPTY_SUMMARY;
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
    <Layout width="lg">
      <div className="flex flex-col gap-4 px-4 pt-4 md:px-0 md:pt-0">
        {user && (
          <div className="flex flex-col gap-4 rounded-2xl border-[0.4px] border-border bg-card p-4">
            <div className="flex items-start gap-8">
              <div className="flex flex-1 flex-col gap-2">
                <div className="flex flex-col gap-1">
                  <span className="text-[9px] text-foreground/80">
                    Total Balance
                  </span>
                  <span className="text-base font-semibold text-foreground">
                    ${summary.totalBalance.toFixed(2)}
                  </span>
                </div>
                <div className="flex flex-wrap items-end gap-x-3 gap-y-1">
                  <div className="flex items-end gap-1">
                    <span className="text-[9px] font-light text-muted-foreground">
                      Vault margin:
                    </span>
                    <span className="text-[10px] font-medium text-foreground">
                      ${summary.freeMargin.toFixed(2)}
                    </span>
                  </div>
                  <div className="flex items-end gap-1">
                    <span className="text-[9px] font-light text-muted-foreground">
                      Wallet USDC:
                    </span>
                    <span className="text-[10px] font-medium text-foreground">
                      ${summary.walletBalance.toFixed(2)}
                    </span>
                  </div>
                  <div className="flex items-end gap-1">
                    <span className="text-[9px] font-light text-muted-foreground">
                      Used margin:
                    </span>
                    <span className="text-[10px] font-medium text-foreground">
                      ${summary.usedMargin.toFixed(2)}
                    </span>
                  </div>
                </div>
              </div>
              <div className="flex w-[88px] flex-col items-end gap-1">
                <span className="text-right text-[9px] font-light text-muted-foreground">
                  Unrealized PnL
                </span>
                <span
                  className={cn(
                    "text-right text-xs font-medium tracking-[-0.12px]",
                    summary.unrealizedPnl >= 0
                      ? "text-success"
                      : "text-destructive",
                  )}
                >
                  {summary.unrealizedPnl >= 0 ? "+" : ""}$
                  {summary.unrealizedPnl.toFixed(2)}
                </span>
              </div>
            </div>

            <div className="flex items-start justify-between">
              <div className="flex flex-col gap-1">
                <span className="text-[9px] text-muted-foreground">
                  Profit/Loss
                </span>
                <span className="text-sm font-semibold text-foreground">
                  ${summary.profitLoss.toFixed(2)}
                </span>
              </div>
              <div className="flex items-center gap-1">
                {pnlPeriods.map((p) => (
                  <button
                    key={p}
                    onClick={() => setPeriod(p)}
                    className={cn(
                      "rounded-md px-2 py-1 text-[10px] font-medium",
                      period === p
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground",
                    )}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-3">
                <button
                  onClick={handleClaim}
                  className="flex flex-1 items-center justify-center gap-1 rounded-lg border-[0.4px] border-border bg-muted px-4 py-2 text-xs font-medium tracking-[-0.12px] text-foreground/80"
                  disabled={isClaiming || isDepositing}
                >
                  <Download className="h-4 w-4" strokeWidth={1.4} />
                  {isClaiming ? "Claiming..." : "Get test USDC"}
                </button>
                <button
                  onClick={handleDeposit}
                  className="flex flex-1 items-center justify-center gap-1 rounded-lg bg-primary px-4 py-2 text-xs font-medium tracking-[-0.12px] text-primary-foreground disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={isDepositing || isClaiming}
                >
                  <Upload className="h-4 w-4" strokeWidth={1.4} />
                  {isDepositing ? "Depositing..." : "Deposit to vault"}
                </button>
              </div>
              <button
                onClick={handleWithdraw}
                disabled
                className="flex items-center justify-center gap-1 rounded-lg border-[0.4px] border-border bg-muted px-4 py-2 text-xs font-medium tracking-[-0.12px] text-foreground/80"
              >
                <Download className="h-4 w-4" strokeWidth={1.4} />
                Withdraw
              </button>
              <p className="text-[9px] leading-[12px] text-muted-foreground">
                Only vault margin can back orders. Depositing moves your wallet
                test-USDC into the CollateralVault. Keep a little Amoy POL in
                this wallet for the approval and deposit gas.
              </p>
            </div>
          </div>
        )}

        {!user ? (
          <EmptyState
            title="Sign in to see your portfolio"
            caption="Your positions, orders and history show here"
          />
        ) : (
          <>
            <SegmentedControl
              value={tab}
              onChange={(v) => setTab(v as Tab)}
              options={[
                { value: "position", label: "Position" },
                { value: "open", label: "Open" },
                { value: "history", label: "History" },
              ]}
            />

            {tab === "position" ? (
              positions.length > 0 ? (
                <div className="flex flex-col gap-2">
                  {positions.map((p) => (
                    <PositionCard key={p.id} position={p} />
                  ))}
                </div>
              ) : (
                <EmptyState
                  title="No open positions"
                  caption="Your running positions show here"
                />
              )
            ) : tab === "open" ? (
              openOrders.length > 0 ? (
                <div className="flex flex-col gap-2">
                  {openOrders.map((o) => (
                    <OpenOrderCard
                      key={o.id}
                      order={o}
                      onCancel={(id) => cancelOrder(id)}
                      cancelling={isCancelling}
                    />
                  ))}
                </div>
              ) : (
                <EmptyState
                  title="No open orders"
                  caption="Your limit orders show here"
                />
              )
            ) : historyOrders.length > 0 ? (
              <div className="flex flex-col gap-2">
                {historyOrders.map((h) => (
                  <HistoryCard key={h.id} order={h} />
                ))}
              </div>
            ) : (
              <EmptyState
                title="No trade history"
                caption="Your closed trades show here"
              />
            )}
          </>
        )}
      </div>

      {showSignIn && (
        <SignInSheet
          basket={getBasket(undefined)}
          onClose={() => setShowSignIn(false)}
        />
      )}
    </Layout>
  );
}
