import { TrendingUp, TrendingDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { OpenOrder } from "@/lib/portfolio-data";

export function OpenOrderCard({
  order,
  onCancel,
  cancelling,
}: {
  order: OpenOrder;
  onCancel?: (orderId: string) => void;
  cancelling?: boolean;
}) {
  const isLong = order.side === "Long";

  return (
    <div className="flex w-full items-center gap-4 rounded-xl border-[0.4px] border-border bg-card p-3">
      <div
        className={cn(
          "flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg",
          isLong ? "bg-success/10" : "bg-destructive/10",
        )}
      >
        {isLong ? (
          <TrendingUp className="h-6 w-6 text-success" strokeWidth={1.6} />
        ) : (
          <TrendingDown
            className="h-6 w-6 text-destructive"
            strokeWidth={1.6}
          />
        )}
      </div>

      <div className="flex flex-1 items-center justify-between">
        <div className="flex flex-col items-start gap-1">
          <div className="flex items-center gap-3">
            <span className="text-xs font-medium tracking-[-0.12px] text-foreground">
              {order.side} • {order.symbol}
            </span>
            <span className="text-[10px] font-medium text-foreground">
              {order.size} @ {order.entry}
            </span>
          </div>
          <div className="flex items-end gap-1">
            <span className="text-[9px] text-muted-foreground">
              {order.date}
            </span>
            <span className="text-[9px] text-muted-foreground">
              {order.time}
            </span>
          </div>
        </div>

        <div className="flex flex-col items-end gap-1">
          <span className="text-xs font-semibold tracking-[-0.12px] text-muted-foreground">
            {order.orderType}
          </span>
          <span className="text-[9px] text-muted-foreground">
            {order.status}
          </span>
          {onCancel && (
            <button
              onClick={() => onCancel(order.id)}
              disabled={cancelling}
              className="rounded-lg border-[0.4px] border-border px-3 py-1 text-[10px] font-medium text-foreground/80"
            >
              {cancelling ? "Cancelling..." : "Cancel"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
