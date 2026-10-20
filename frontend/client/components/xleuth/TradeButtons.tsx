import { cn } from "@/lib/utils";

export function TradeButtons({
  onSell,
  onBuy,
  variant = "floating",
}: {
  onSell: () => void;
  onBuy: () => void;
  /** `floating` is the mobile action bar; `inline` is the desktop order-rail row. */
  variant?: "floating" | "inline";
}) {
  return (
    <div
      className={cn(
        variant === "floating"
          ? "fixed inset-x-0 bottom-16 z-20 mx-auto flex w-full max-w-md justify-center gap-3 bg-neutral-950 px-4 py-3 md:hidden"
          : "flex w-full justify-center gap-3",
      )}
    >
      <button
        onClick={onSell}
        className="flex-1 rounded-xl border-[0.2px] border-destructive bg-destructive/10 px-4 py-3 text-base font-semibold text-destructive"
      >
        Sell
      </button>
      <button
        onClick={onBuy}
        className="flex-1 rounded-xl border-[0.2px] border-success bg-success/10 px-4 py-3 text-base font-semibold text-success"
      >
        Buy
      </button>
    </div>
  );
}
