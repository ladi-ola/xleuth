import { useState } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Basket } from "@/lib/market-data";
import { usePositions, usePortfolioSummary } from "@/lib/api/hooks";

const LEVERAGE_OPTIONS = [1, 2, 3, 4, 5] as const;
const QUICK_PERCENTAGES = [25, 50, 75, 100] as const;
const ORDER_TYPES = ["Market", "Limit", "Stop"] as const;
const MIN_SIZE = 10;

export function TradeModal({
  basket,
  initialSide,
  onClose,
  onSubmitted,
}: {
  basket: Basket;
  initialSide: "buy" | "sell";
  onClose: () => void;
  onSubmitted: (order: {
    side: "buy" | "sell";
    amount: number;
    leverage: number;
    slippageBps: number;
  }) => void;
}) {
  const [side, setSide] = useState<"buy" | "sell">(initialSide);
  const [orderType, setOrderType] = useState<(typeof ORDER_TYPES)[number]>("Market");
  const [leverage, setLeverage] = useState<number>(2);
  const [amount, setAmount] = useState("");
  const [takeProfit, setTakeProfit] = useState("");
  const [stopLoss, setStopLoss] = useState("");
  // Phase 6: market orders require max_slippage_bps (0-10000). The UI had no
  // slippage control, so this input collects it using the existing styles.
  const [slippage, setSlippage] = useState("100");

  // Phase 7: live position and margin. basket.listName carries the backend
  // basket_name, so the current position is the one on this basket, if any.
  const { data: positionsData } = usePositions();
  const { data: summaryData } = usePortfolioSummary();
  const livePosition = positionsData?.positions.find((p) => p.basket_name === basket.listName);
  const positionSide = livePosition
    ? livePosition.side === "buy" || livePosition.side === "long"
      ? "Long"
      : "Short"
    : null;
  const positionPnl = livePosition?.unrealized_pnl_abs ?? 0;

  const notional = Number(amount) || 0;
  const marginRequired = notional / leverage;
  const availableBefore = summaryData?.free_margin ?? 0;
  const freeAfterOrder = availableBefore - marginRequired;

  const handlePercentage = (pct: number) => {
    const maxNotional = availableBefore * leverage;
    setAmount(((maxNotional * pct) / 100).toFixed(2));
  };

  const handleSubmit = () => {
    // TP/SL fields are intentionally not sent: the API attaches SL/TP to an
    // existing position (position_id required), which does not exist yet at
    // entry. See the Phase 6 report for the proposed attach flow.
    onSubmitted({ side, amount: notional, leverage, slippageBps: Number(slippage) || 0 });
  };

  return (
    <div className="fixed inset-0 z-50 mx-auto flex max-w-md items-end justify-center">
      <div className="absolute inset-0 bg-neutral-950/88 backdrop-blur-[6px]" onClick={onClose} />
      <div className="no-scrollbar relative flex max-h-[92vh] w-full max-w-[370px] flex-col gap-2 overflow-y-auto rounded-3xl border-[0.8px] border-neutral-600 bg-neutral-800 p-4 pt-6 mb-4">
        <div className="flex items-center justify-between">
          <span className="text-base font-semibold leading-6 text-neutral-100">Trade</span>
          <button onClick={onClose} aria-label="Close">
            <X className="h-4 w-4 p-1 text-neutral-500" strokeWidth={1.4} />
          </button>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-neutral-200">{basket.symbol}</span>
          <span className="text-[9px] font-light text-neutral-400">Amoy Testnet</span>
        </div>

        <div className="flex flex-col gap-2 py-2">
          <span className="text-xs font-medium text-neutral-300">Current Position</span>
          <div className="flex items-center justify-between">
            <span className="text-xs text-neutral-400">
              {livePosition
                ? `${positionSide} ${livePosition.size} @ ${livePosition.entry_price}`
                : "No open position"}
            </span>
            <span
              className={cn(
                "text-base font-semibold",
                positionPnl >= 0 ? "text-success" : "text-destructive",
              )}
            >
              {positionPnl >= 0 ? "+" : ""}
              {positionPnl.toFixed(2)}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-0.5 rounded-xl border-[0.4px] border-neutral-600 bg-neutral-800 p-0.5">
          <button
            onClick={() => setSide("buy")}
            className={cn(
              "flex-1 rounded-[10px] py-2 text-[10px] font-medium",
              side === "buy" ? "bg-success/10 text-success" : "text-neutral-500",
            )}
          >
            BUY
          </button>
          <button
            onClick={() => setSide("sell")}
            className={cn(
              "flex-1 rounded-[10px] py-2 text-[10px] font-medium",
              side === "sell" ? "bg-destructive/10 text-destructive" : "text-neutral-500",
            )}
          >
            SELL
          </button>
        </div>

        <div className="flex items-center justify-between rounded-lg border-[0.4px] border-neutral-600 px-3 py-2.5">
          <span className="text-xs text-neutral-400">Index Price</span>
          <span className="text-xs font-medium text-neutral-100">{basket.price}</span>
        </div>

        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-neutral-200">Size (USDC Notional)</span>
          <div className="flex items-center justify-between gap-2 rounded-lg border-[0.4px] border-neutral-600 bg-neutral-800 px-3 py-2.5">
            <input
              type="number"
              min={0}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0.00"
              className="w-full min-w-0 bg-transparent text-right text-sm text-neutral-100 outline-none placeholder:text-neutral-500"
            />
            <span className="flex-shrink-0 whitespace-nowrap text-sm text-neutral-500">
              USDC
            </span>
          </div>
          <span className="text-[9px] text-neutral-500">Min size: {MIN_SIZE} USDC</span>
        </div>

        <div className="flex items-center gap-2">
          {ORDER_TYPES.map((type) => (
            <button
              key={type}
              onClick={() => type === "Market" && setOrderType(type)}
              disabled={type !== "Market"}
              className={cn(
                "flex-1 rounded-[10px] py-2 text-[10px] font-medium",
                orderType === type ? "bg-neutral-950 text-neutral-50" : "text-neutral-600",
              )}
            >
              {type}
            </button>
          ))}
        </div>

        <div className="flex flex-col gap-3 rounded-xl border-[0.4px] border-neutral-600 p-3">
          <span className="text-sm font-medium text-neutral-200">Leverage</span>
          <span className="text-sm font-semibold text-neutral-100">{leverage}x</span>
        </div>

        <div className="flex flex-col gap-3 rounded-xl border-[0.4px] border-neutral-600 p-3">
          <span className="text-sm font-medium text-neutral-200">TP/SL</span>
          <div className="flex items-center gap-2">
            <input
              type="number"
              value={takeProfit}
              onChange={(e) => setTakeProfit(e.target.value)}
              placeholder="Take Profit"
              className="w-full rounded-lg border-[0.4px] border-neutral-600 bg-neutral-800 px-3 py-2 text-xs text-neutral-100 outline-none placeholder:text-neutral-500 focus:border-primary"
            />
            <input
              type="number"
              value={stopLoss}
              onChange={(e) => setStopLoss(e.target.value)}
              placeholder="Stop Loss"
              className="w-full rounded-lg border-[0.4px] border-neutral-600 bg-neutral-800 px-3 py-2 text-xs text-neutral-100 outline-none placeholder:text-neutral-500 focus:border-primary"
            />
          </div>
        </div>

        <div className="flex flex-col gap-2 rounded-xl border-[0.4px] border-[#8855FF]/30 bg-[#8855FF]/10 p-3">
          <span className="text-sm font-semibold text-neutral-100">Order Summary</span>
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-neutral-400">Notional</span>
            <span className="text-[10px] font-medium text-neutral-100">
              ${notional.toFixed(2)}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-neutral-400">Margin required</span>
            <span className="text-[10px] font-medium text-neutral-100">
              ${marginRequired.toFixed(2)}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-neutral-400">Free after order</span>
            <span className="text-[10px] font-medium text-neutral-100">
              ${freeAfterOrder.toFixed(2)}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-neutral-400">Max slippage (bps)</span>
            <input
              type="number"
              min={1}
              max={10000}
              value={slippage}
              onChange={(e) => setSlippage(e.target.value)}
              placeholder="100"
              className="w-20 bg-transparent text-right text-[10px] font-medium text-neutral-100 outline-none placeholder:text-neutral-500"
            />
          </div>
        </div>

        <button
          onClick={handleSubmit}
          className={cn(
            "mt-1 rounded-xl px-4 py-3 text-base font-semibold text-white",
            side === "buy" ? "bg-success" : "bg-destructive",
          )}
        >
          Place {side === "buy" ? "Buy" : "Sell"} Order
        </button>

        <p className="text-center text-[9px] leading-[13px] text-neutral-500">
          Fill or Kill policy. Order will be executed at market conditions, difference with
          requested price may be significant!
        </p>
      </div>
    </div>
  );
}