import { useRef, useState } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import { track } from "@/lib/analytics";
import type { Basket } from "@/lib/market-data";
import { usePositions, usePortfolioSummary } from "@/lib/api/hooks";
import { MIN_ORDER_USDC, formatUsdc } from "@/lib/api/limits";

const LEVERAGE_OPTIONS = [1, 2, 3, 4, 5] as const;
const QUICK_PERCENTAGES = [25, 50, 75, 100] as const;

export type TradeOrderType = "market" | "limit" | "stop";

const ORDER_TYPES: { value: TradeOrderType; label: string }[] = [
  { value: "market", label: "Market" },
  { value: "limit", label: "Limit" },
  { value: "stop", label: "Stop" },
];

export interface TradeSubmission {
  side: "buy" | "sell";
  orderType: TradeOrderType;
  /** USDC notional entered by the user. */
  amount: number;
  leverage: number;
  /** Required by the API for market/stop orders; ignored for limit orders. */
  slippageBps: number;
  /** Resting price for limit orders. */
  limitPrice?: number;
  /** Trigger price for stop orders. */
  triggerPrice?: number;
  /** TP/SL apply to an existing position (the API needs a position_id). */
  takeProfit?: number;
  stopLoss?: number;
  positionId?: string;
  idempotencyKey: string;
}

function formatPrice(price: number): string {
  return price.toLocaleString("en-US", {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  });
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[10px] font-light text-neutral-300">{label}</span>
      <span className="text-[10px] font-medium text-white">{value}</span>
    </div>
  );
}

export function TradeModal({
  basket,
  initialSide,
  onClose,
  onSubmitted,
}: {
  basket: Basket;
  initialSide: "buy" | "sell";
  onClose: () => void;
  onSubmitted: (order: TradeSubmission) => void;
}) {
  // Task 15: one idempotency key per modal session — double-clicks and
  // in-flight retries dedupe server-side; a fresh modal means a new intent.
  const idempotencyKey = useRef(
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`,
  );
  const [side, setSide] = useState<"buy" | "sell">(initialSide);
  const [orderType, setOrderType] = useState<TradeOrderType>("market");
  const [leverage, setLeverage] = useState<number>(2);
  const [amount, setAmount] = useState("");
  // Limit price / stop trigger price (the API requires one of them per type).
  const [orderPrice, setOrderPrice] = useState("");
  const [takeProfit, setTakeProfit] = useState("");
  const [stopLoss, setStopLoss] = useState("");
  // Market/stop orders require max_slippage_bps (0-10000).
  const [slippage, setSlippage] = useState("100");

  // Phase 7: live position and margin. basket.listName carries the backend
  // basket_name, so the current position is the one on this basket, if any.
  const { data: positionsData } = usePositions();
  const { data: summaryData } = usePortfolioSummary();
  const livePosition = positionsData?.positions.find((p) => p.basket_name === basket.listName);
  const hasPosition = !!livePosition;
  const positionSide = livePosition
    ? livePosition.side.toLowerCase() === "buy" || livePosition.side.toLowerCase() === "long"
      ? "Long"
      : "Short"
    : null;
  const positionPnl = livePosition?.unrealized_pnl_abs ?? 0;

  const notional = Number(amount) || 0;
  const priceValue = Number(orderPrice) || 0;
  const slippageBps = Math.floor(Number(slippage) || 0);
  const marginRequired = notional / leverage;
  const availableBefore = summaryData?.free_margin ?? 0;
  const freeAfterOrder = availableBefore - marginRequired;

  // MIN_ORDER_SIZE is a USDC notional floor. The order request converts it to
  // contracts (size = notional / indexPrice), so validate the amount directly
  // instead of comparing a contract count to a USDC value.
  const hasLivePrice = basket.price > 0;

  const needsPrice = orderType !== "market";
  const needsSlippage = orderType !== "limit";
  const priceLabel = orderType === "limit" ? "Limit Price" : "Trigger Price";

  // Task 15: client-side validation is UX only — the matching engine
  // re-validates everything server-side (min size, tick, margin, slippage).
  const amountError =
    !hasLivePrice ? "Waiting for a live index price to size this order." :
    notional <= 0 ? "Enter an amount greater than 0." :
    notional < MIN_ORDER_USDC
      ? `Minimum order is $${formatUsdc(MIN_ORDER_USDC)} USDC.`
      : null;
  const priceError = needsPrice && priceValue <= 0 ? "Enter a price greater than 0." : null;
  const slippageError =
    needsSlippage && (slippageBps < 1 || slippageBps > 10000)
      ? "Slippage must be 1–10000 bps."
      : null;
  const takeProfitError =
    hasPosition && takeProfit !== "" && !(Number(takeProfit) > 0)
      ? "Take profit must be greater than 0."
      : null;
  const stopLossError =
    hasPosition && stopLoss !== "" && !(Number(stopLoss) > 0)
      ? "Stop loss must be greater than 0."
      : null;
  const formInvalid =
    amountError !== null ||
    priceError !== null ||
    slippageError !== null ||
    takeProfitError !== null ||
    stopLossError !== null;

  // Quick-size buttons size the notional to a share of available margin at the
  // selected leverage (max notional = free margin x leverage).
  const handlePercentage = (pct: number) => {
    const maxNotional = availableBefore * leverage;
    setAmount(((maxNotional * pct) / 100).toFixed(2));
  };

  const handleOrderType = (next: TradeOrderType) => {
    setOrderType(next);
    // Pre-fill the price with the live index price the first time Limit/Stop is
    // chosen so the field is never empty by default. Two decimals keeps the
    // default on the engine's 0.01 tick; the user can still type any price.
    if (next !== "market" && orderPrice === "") {
      setOrderPrice(basket.price > 0 ? basket.price.toFixed(2) : "");
    }
  };

  const handleSubmit = () => {
    if (formInvalid) return; // submit is also disabled; belt and suspenders
    track("order_submitted");
    onSubmitted({
      side,
      orderType,
      amount: notional,
      leverage,
      slippageBps,
      limitPrice: orderType === "limit" ? priceValue : undefined,
      triggerPrice: orderType === "stop" ? priceValue : undefined,
      takeProfit: hasPosition && takeProfit !== "" ? Number(takeProfit) : undefined,
      stopLoss: hasPosition && stopLoss !== "" ? Number(stopLoss) : undefined,
      positionId: hasPosition ? livePosition.position_id : undefined,
      idempotencyKey: idempotencyKey.current,
    });
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Trade"
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
    >
      <div className="absolute inset-0 bg-neutral-950/88 backdrop-blur-[6px]" onClick={onClose} />
      <div className="no-scrollbar relative flex max-h-[92vh] w-full max-w-[370px] flex-col gap-2 overflow-y-auto rounded-3xl border-[0.8px] border-neutral-600 bg-neutral-800 px-4 py-6 md:max-w-md">
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
            <span className="text-xs font-normal text-neutral-400">
              {livePosition
                ? `${positionSide} ${livePosition.size} @ ${livePosition.entry_price.toFixed(2)}`
                : "No open position"}
            </span>
            {livePosition && (
              <span
                className={cn(
                  "text-base font-semibold",
                  positionPnl >= 0 ? "text-success" : "text-destructive",
                )}
              >
                {positionPnl >= 0 ? "+" : ""}
                {positionPnl.toFixed(2)}
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-0.5 rounded-xl border-[0.4px] border-neutral-600 bg-neutral-800 p-0.5">
          <button
            onClick={() => setSide("buy")}
            aria-pressed={side === "buy"}
            className={cn(
              "flex-1 rounded-[10px] py-2 text-[10px] font-medium transition-colors",
              side === "buy" ? "bg-success/10 text-success" : "text-neutral-500",
            )}
          >
            BUY
          </button>
          <button
            onClick={() => setSide("sell")}
            aria-pressed={side === "sell"}
            className={cn(
              "flex-1 rounded-[10px] py-2 text-[10px] font-medium transition-colors",
              side === "sell" ? "bg-destructive/10 text-destructive" : "text-neutral-500",
            )}
          >
            SELL
          </button>
        </div>

        <div className="flex items-center gap-0.5 rounded-xl border-[0.4px] border-neutral-600 bg-neutral-800 p-0.5">
          {ORDER_TYPES.map((type) => (
            <button
              key={type.value}
              onClick={() => handleOrderType(type.value)}
              aria-pressed={orderType === type.value}
              className={cn(
                "flex-1 rounded-[10px] py-2 text-[10px] font-medium transition-colors",
                orderType === type.value
                  ? "bg-[#020003] text-neutral-50"
                  : "text-neutral-500",
              )}
            >
              {type.label}
            </button>
          ))}
        </div>

        <div className="flex items-center justify-between rounded-xl border-[0.4px] border-neutral-600 bg-neutral-950 px-3 py-3">
          <span className="text-[10px] font-medium text-neutral-500">
            {needsPrice ? priceLabel : "Index Price"}
          </span>
          {needsPrice ? (
            <input
              type="number"
              inputMode="decimal"
              min={0}
              value={orderPrice}
              onChange={(e) => setOrderPrice(e.target.value)}
              placeholder={basket.price > 0 ? basket.price.toFixed(2) : "0.000"}
              aria-label={priceLabel}
              className="w-28 bg-transparent text-right text-[10px] font-medium text-neutral-100 outline-none placeholder:text-neutral-500"
            />
          ) : (
            <span className="text-[10px] font-medium text-neutral-300">
              {formatPrice(basket.price)}
            </span>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-neutral-300">Size (USDC Notional)</span>
          <div className="flex items-center gap-2 rounded-xl border-[0.4px] border-neutral-600 bg-neutral-950 px-3 py-3 focus-within:border-neutral-500">
            <input
              type="number"
              inputMode="decimal"
              min={0}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0.00"
              aria-label="Size in USDC notional"
              className="w-full min-w-0 bg-transparent text-right text-[10px] font-medium text-neutral-100 outline-none placeholder:text-neutral-500"
            />
            <span className="flex-shrink-0 whitespace-nowrap text-[10px] font-medium text-neutral-500">
              USDC
            </span>
          </div>
          <span className="text-[9px] font-normal text-neutral-500">
            Min order: ${formatUsdc(MIN_ORDER_USDC)} USDC
          </span>
          {amountError && (
            <span role="alert" className="text-[9px] text-destructive">{amountError}</span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {QUICK_PERCENTAGES.map((pct) => (
            <button
              key={pct}
              onClick={() => handlePercentage(pct)}
              className="flex-1 rounded-[10px] bg-neutral-950 py-2.5 text-[10px] font-medium text-neutral-400 transition-colors hover:text-neutral-200"
            >
              {pct === 100 ? "Max" : `${pct}%`}
            </button>
          ))}
        </div>

        <div className="flex flex-col gap-3 rounded-xl border-[0.4px] border-neutral-600 bg-neutral-950 p-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-neutral-300">Leverage</span>
            <span className="text-xs font-medium text-neutral-200">{leverage}x</span>
          </div>
          <div className="flex items-center gap-2">
            {LEVERAGE_OPTIONS.map((lev) => (
              <button
                key={lev}
                onClick={() => setLeverage(lev)}
                aria-pressed={leverage === lev}
                className={cn(
                  "flex-1 rounded-lg py-1.5 text-[10px] font-medium transition-colors",
                  leverage === lev
                    ? "bg-neutral-700 text-neutral-100"
                    : "text-neutral-400 hover:text-neutral-200",
                )}
              >
                {lev}x
              </button>
            ))}
          </div>
        </div>

        <div
          className={cn(
            "flex flex-col gap-2 rounded-xl border-[0.4px] border-neutral-600 bg-neutral-950 p-3",
            !hasPosition && "opacity-60",
          )}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-neutral-300">TP/SL</span>
            {!hasPosition && (
              <span className="text-[9px] text-neutral-500">Open a position to set</span>
            )}
          </div>
          <div className="flex items-center gap-4">
            <input
              type="number"
              inputMode="decimal"
              min={0}
              value={takeProfit}
              onChange={(e) => setTakeProfit(e.target.value)}
              disabled={!hasPosition}
              placeholder="Take Profit"
              aria-label="Take profit price"
              className="h-6 w-full rounded-lg bg-neutral-800 px-3 text-[9px] text-neutral-100 outline-none placeholder:text-neutral-500 disabled:cursor-not-allowed disabled:opacity-70"
            />
            <input
              type="number"
              inputMode="decimal"
              min={0}
              value={stopLoss}
              onChange={(e) => setStopLoss(e.target.value)}
              disabled={!hasPosition}
              placeholder="Stop Loss"
              aria-label="Stop loss price"
              className="h-6 w-full rounded-lg bg-neutral-800 px-3 text-[9px] text-neutral-100 outline-none placeholder:text-neutral-500 disabled:cursor-not-allowed disabled:opacity-70"
            />
          </div>
          {takeProfitError && (
            <span role="alert" className="text-[9px] text-destructive">{takeProfitError}</span>
          )}
          {stopLossError && (
            <span role="alert" className="text-[9px] text-destructive">{stopLossError}</span>
          )}
        </div>

        <div className="flex flex-col gap-2 rounded-xl border-[0.2px] border-[#8855FF] bg-[#8855FF]/10 p-3">
          <span className="text-xs font-medium text-neutral-200">Order Summary</span>
          <SummaryRow label="Notional" value={`$${notional.toFixed(2)}`} />
          <SummaryRow label="Margin required" value={`$${marginRequired.toFixed(2)}`} />
          <SummaryRow label="Available required" value={`$${availableBefore.toFixed(2)}`} />
          <SummaryRow label="Free after order" value={`$${freeAfterOrder.toFixed(2)}`} />
          {needsSlippage && (
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-light text-neutral-300">Max slippage (bps)</span>
              <input
                type="number"
                min={1}
                max={10000}
                value={slippage}
                onChange={(e) => setSlippage(e.target.value)}
                placeholder="100"
                aria-label="Max slippage in basis points"
                className="w-20 bg-transparent text-right text-[10px] font-medium text-white outline-none placeholder:text-neutral-500"
              />
            </div>
          )}
          {slippageError && (
            <span role="alert" className="text-[9px] text-destructive">{slippageError}</span>
          )}
        </div>

        <button
          onClick={handleSubmit}
          disabled={formInvalid}
          aria-disabled={formInvalid}
          className={cn(
            "mt-1 rounded-lg px-4 py-2 text-xs font-normal text-white transition-opacity",
            formInvalid && "cursor-not-allowed opacity-40",
            !formInvalid && side === "buy" && "bg-success",
            !formInvalid && side === "sell" && "bg-destructive",
          )}
        >
          Place {side === "buy" ? "Buy" : "Sell"} Order
        </button>

        <p className="text-center text-[9px] leading-[10px] text-neutral-500">
          Fill or Kill policy. Order will be executed at market conditions, difference with
          requested price may be significant!
        </p>
      </div>
    </div>
  );
}
