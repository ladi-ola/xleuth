import { useState } from "react";
import { Download, Upload } from "lucide-react";
import { useDynamicContext } from "@dynamic-labs/sdk-react-core";
import { track } from "@/lib/analytics";
import {
  useAccount,
  useCancelOrder,
  useFaucetClaim,
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
};

export default function Portfolio() {
  usePageMeta({ title: 'Portfolio — Xleuth (testnet)', description: 'Track test-USDC balances, open positions, orders and trade history on the Polygon Amoy testnet.', path: '/portfolio' });
  const [tab, setTab] = useState<Tab>("position");
  const [period, setPeriod] = useState<PnlPeriod>("YTD");
  const [showSignIn, setShowSignIn] = useState(false);
  const { user } = useDynamicContext();
  const { toast } = useToast();
  const { mutate: claimFaucet, isPending } = useFaucetClaim();
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

  const summary = summaryData ? adaptPortfolioSummary(summaryData) : EMPTY_SUMMARY;
  const positions: Position[] = positionsData?.positions.map(adaptPosition) ?? [];
  const openOrders: OpenOrder[] = openOrdersData?.orders.map(adaptOpenOrder) ?? [];
  const tradeHistory: HistoryOrder[] = historyData?.orders.map(adaptHistoryOrder) ?? [];
  const transferHistory: HistoryOrder[] = (transactionsData?.transactions ?? [])
    .map(adaptTransaction)
    .filter((entry) => entry.kind === "transfer");
  const historyOrders: HistoryOrder[] = [...tradeHistory, ...transferHistory];

  const handleDeposit = async () => {
    if (!user) return setShowSignIn(true);
    try {
      track("deposit_submitted");
      await claimFaucet();
      toast({ title: "Faucet claim successful", description: "Test USDC deposited", variant: "destructive" });
    } catch (error) {
      if (error?.status === 429 || error?.code === 'cooldown') {
        const retryAfter = error?.retryAfter || 86400;
        toast({ title: "Faucet on cooldown", description: `Try again in ${Math.ceil(retryAfter / 3600)} hours.`, variant: "destructive" });
      } else if (error?.status === 401 || error?.code === 'token_missing' || error?.code === 'token_invalid' || error?.code === 'token_expired') {
        toast({ title: "Authentication error", description: "Please sign in again.", variant: "destructive" });
      } else if (error?.code === 'settlement_failed' || error?.code === 'faucet_depleted') {
        toast({ title: "Faucet depleted", description: error?.message || "Faucet is out of funds.", variant: "destructive" });
      } else if (error?.message) {
        toast({ title: "Claim failed", description: error.message, variant: "destructive" });
      } else {
        toast({ title: "Claim failed", description: "Unknown error occurred.", variant: "destructive" });
      }
    }
  };

  const handleWithdraw = () => {
    // Withdraw is explicitly out of scope for this batch.
    toast({ title: "Withdraw coming soon", description: "This flow isn't wired up yet." });
  };

  return (
    <Layout>
      <div className="flex flex-col gap-4 px-4 pt-4">
        {user ? (
          <div className="flex flex-col gap-4 rounded-2xl border-[0.4px] border-neutral-600 bg-neutral-900 p-4">
            <div className="flex items-start gap-8">
              <div className="flex flex-1 flex-col gap-2">
                <div className="flex flex-col gap-1">
                  <span className="text-[9px] font-medium text-neutral-500">Total Balance</span>
                  <span className="text-base font-semibold text-neutral-100">
                    ${summary.totalBalance.toFixed(2)}
                  </span>
                </div>
                <div className="flex items-end gap-3">
                  <div className="flex items-end gap-1">
                    <span className="text-[9px] font-light text-neutral-400">Free margin:</span>
                    <span className="text-[10px] font-medium text-neutral-100">
                      ${summary.freeMargin.toFixed(2)}
                    </span>
                  </div>
                  <div className="flex items-end gap-1">
                    <span className="text-[9px] font-light text-neutral-400">Used margin:</span>
                    <span className="text-[10px] font-medium text-neutral-100">
                      ${summary.usedMargin.toFixed(2)}
                    </span>
                  </div>
                </div>
              </div>

              <div className="flex w-[88px] flex-col items-end gap-1">
                <span className="text-right text-[9px] font-light text-neutral-400">
                  Unrealized PnL
                </span>
                <span
                  className={cn(
                    "text-right text-xs font-medium tracking-[-0.12px]",
                    summary.unrealizedPnl >= 0 ? "text-success" : "text-destructive",
                  )}
                >
                  {summary.unrealizedPnl >= 0 ? "+" : ""}$
                  {summary.unrealizedPnl.toFixed(2)}
                </span>
              </div>
            </div>

            <div className="flex items-start justify-between">
              <div className="flex flex-col gap-1">
                <span className="text-[9px] text-neutral-400">Profit/Loss</span>
                <span className="text-sm font-semibold text-neutral-100">
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
                      period === p ? "bg-primary-dark text-neutral-50" : "text-neutral-400",
                    )}
                  >
                    {p}
                  </button>
                ))
              }
              </div>
            </div>
          </div>
        ) : (
          <EmptyState
            title="Sign in to see your portfolio"
            caption="Your positions, orders and history show here"
          />
        )}

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
            <EmptyState title="No open positions" caption="Your running positions show here" />
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
            <EmptyState title="No open orders" caption="Your limit orders show here" />
          )
        ) : historyOrders.length > 0 ? (
          <div className="flex flex-col gap-2">
            {historyOrders.map((h) => (
              <HistoryCard key={h.id} order={h} />
            ))}
          </div>
        ) : (
          <EmptyState title="No trade history" caption="Your closed trades show here" />
        )}

        {user ? (
          <div className="flex items-center gap-3">
            <button
              onClick={handleDeposit}
              className="flex flex-1 items-center justify-center gap-1 rounded-lg bg-primary px-4 py-2 text-xs font-medium tracking-[-0.12px] text-neutral-50"
              disabled={isPending}
            >
              <Download className="h-4 w-4" strokeWidth={1.4} />
              Deposit
            </button>
            <button
              onClick={handleWithdraw}
              disabled
              className="flex flex-1 items-center justify-center gap-1 rounded-lg border-[0.4px] border-neutral-600 bg-neutral-800 px-4 py-2 text-xs font-medium tracking-[-0.12px] text-neutral-300"
            >
              <Upload className="h-4 w-4" strokeWidth={1.4} />
              Withdraw
            </button>
          </div>
        ) : null}

        {showSignIn && (
          <SignInSheet basket={getBasket(undefined)} onClose={() => setShowSignIn(false)} />
        )}
      </div>
    </Layout>
  );
}
