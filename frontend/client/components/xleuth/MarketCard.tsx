import { Link } from "react-router-dom";
import type { Basket } from "@/lib/market-data";
import { PriceChange } from "./PriceChange";

const STATUS_STYLES: Record<Basket["status"], { bg: string; text: string; dot: string; label: string }> = {
  active: { bg: "bg-success/10", text: "text-success", dot: "bg-success", label: "ACTIVE" },
  upcoming: { bg: "bg-warning/10", text: "text-warning", dot: "bg-warning", label: "UPCOMING" },
  resolved: { bg: "bg-neutral-400/20", text: "text-neutral-400", dot: "bg-neutral-400", label: "RESOLVED" },
};

export function MarketCard({ basket }: { basket: Basket }) {
  const status = STATUS_STYLES[basket.status];
  const tradable = basket.status !== "upcoming";
  const tradeClassName =
    basket.status === "active"
      ? "flex h-8 items-center justify-center rounded-lg bg-primary px-4 text-xs text-white"
      : "flex h-8 items-center justify-center rounded-lg bg-neutral-700 px-4 text-xs text-neutral-500";

  return (
    <div className="flex flex-col gap-8 rounded-2xl border-[0.4px] border-neutral-600 bg-neutral-900 p-4">
      <div className="flex items-start justify-between gap-16">
        <div className="flex min-w-0 w-auto flex-col items-start gap-2 self-center mr-auto">
          <div className="flex w-auto items-center gap-2 self-center mr-auto">
            <span className="text-sm font-semibold text-neutral-200">{basket.listName}</span>
            <span className={`flex items-center gap-1 rounded-lg px-2 py-0.5 ${status.bg}`}>
              <span className={`h-1 w-1 rounded-full ${status.dot}`} />
              <span className={`text-[9px] font-medium leading-[10px] ${status.text}`}>
                {status.label}
              </span>
            </span>
          </div>
          <div className="flex w-[195px] items-center gap-2 self-center mr-auto">
            <p className="flex-1 w-auto self-stretch text-justify text-[9px] font-light leading-[10px] text-neutral-400">
              {basket.description}
            </p>
          </div>
        </div>
        <div className="flex flex-shrink-0 flex-col items-end gap-1">
          <span className="text-sm font-semibold text-neutral-100">{basket.priceLabel}</span>
          <PriceChange
            abs={basket.changeAbs}
            pct={basket.changePct}
            muted={basket.status === "resolved"}
          />
        </div>
      </div>

      <div className="flex items-end justify-between">
        <div className="flex flex-col items-start gap-2.5">
          <div className="flex flex-col items-start gap-1">
            <span className="text-[9px] font-light text-neutral-400">Resolves on</span>
            <span className="text-xs font-medium text-neutral-200">{basket.resolvesOn}</span>
          </div>
          <span className="text-[10px] font-medium text-neutral-300">Vol. {basket.vol}</span>
        </div>
        {tradable ? (
          <Link
            to={`/market/${basket.slug}`}
            className={tradeClassName}
          >
            Trade
          </Link>
        ) : (
          <span className="flex h-8 cursor-not-allowed items-center justify-center rounded-lg bg-neutral-700 px-4 text-xs text-neutral-400">
            Trade
          </span>
        )}
      </div>
    </div>
  );
}
