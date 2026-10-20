import { CircleCheck, MoveLeft, X } from "lucide-react";
import type { Basket } from "@/lib/market-data";

export function OrderResultModal({
  basket,
  order,
  onClose,
}: {
  basket: Basket;
  order: { side: "buy" | "sell"; amount: number; leverage: number };
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      <div className="absolute inset-0 bg-neutral-950/88 backdrop-blur-[5px]" onClick={onClose} />
      <div className="relative flex w-full max-w-md flex-col gap-8 rounded-2xl border-[0.4px] border-neutral-600 bg-neutral-900">
        <div className="flex flex-col gap-2.5 border-b-[0.4px] border-neutral-600 px-5 pb-3 pt-5">
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
        </div>

        <div className="flex flex-col gap-2.5 px-4 pb-4">
          <div className="flex flex-col gap-2.5 rounded-xl border-[0.4px] border-success bg-success/10 p-3">
            <div className="flex items-center gap-2">
              <CircleCheck className="h-4 w-4 text-success" strokeWidth={1.4} />
              <span className="text-xs font-medium text-success">Order filled</span>
            </div>
            <div className="flex flex-col gap-1.5 px-6">
              <span className="text-[10px] font-medium leading-3 text-neutral-50">
                Position order filled
              </span>
              <span className="text-[9px] font-light leading-[10px] text-neutral-200">
                position_order_filled
              </span>
              <span className="text-[10px] font-medium leading-3 text-neutral-50">
                {order.side === "buy" ? "Long" : "Short"} {order.amount || 0} at {order.leverage}x
                &nbsp;| Entry price: {basket.price.toFixed(2)} | SL: | TP:
              </span>
            </div>
            <button onClick={onClose} className="flex items-center gap-2">
              <MoveLeft className="h-4 w-4 text-primary" strokeWidth={1.2} />
              <span className="text-[10px] text-primary">Back</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
