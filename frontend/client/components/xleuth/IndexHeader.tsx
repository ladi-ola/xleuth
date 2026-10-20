import type { Basket } from "@/lib/market-data";
import { cn } from "@/lib/utils";
import { PriceChange } from "./PriceChange";

export function IndexHeader({
  basket,
  className,
}: {
  basket: Basket;
  className?: string;
}) {
  const statusLabel = basket.status.toUpperCase();
  const statusTone =
    basket.status === "active"
      ? "bg-success/10 text-success"
      : basket.status === "upcoming"
        ? "bg-warning/10 text-warning"
        : "bg-neutral-700/40 text-neutral-400";
  const dotTone =
    basket.status === "active"
      ? "bg-success"
      : basket.status === "upcoming"
        ? "bg-warning"
        : "bg-neutral-400";
  return (
    <div className={cn("flex items-start justify-between px-4 pt-5", className)}>
      <div className="flex flex-col items-start gap-1">
        <span className={`flex items-center gap-1 rounded-lg px-2 py-0.5 ${statusTone}`}>
          <span className={`h-1 w-1 rounded-full ${dotTone}`} />
          <span className="text-[9px] font-medium leading-[10px]">{statusLabel}</span>
        </span>
        <span className="text-base font-semibold leading-6 text-white">
          {basket.symbol}
        </span>
        <span className="text-[9px] leading-[10px] text-neutral-400">
          {basket.updatedLabel}
        </span>
      </div>
      <div className="flex flex-col items-end gap-1">
        <span className="text-2xl font-semibold leading-[30px] tracking-[-0.15px] text-white">
          {basket.priceLabel}
        </span>
        <PriceChange abs={basket.changeAbs} pct={basket.changePct} />
      </div>
    </div>
  );
}
