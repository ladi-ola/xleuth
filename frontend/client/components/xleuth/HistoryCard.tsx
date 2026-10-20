import { TrendingUp, TrendingDown, Download, Upload } from "lucide-react";
import { cn } from "@/lib/utils";
import type { HistoryOrder } from "@/lib/portfolio-data";

function formatAmount(value: number) {
  const sign = value >= 0 ? "+" : "-";
  return `${sign}$${Math.abs(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function HistoryCard({ order }: { order: HistoryOrder }) {
  const isPending = order.status === "Pending";

  if (order.kind === "transfer") {
    const isDeposit = order.type === "Deposit";

    return (
      <div className="flex w-full items-center gap-4 rounded-xl border-[0.4px] border-border bg-card p-3">
        <div
          className={cn(
            "flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg",
            isDeposit ? "bg-success/10" : "bg-destructive/10",
          )}
        >
          {isDeposit ? (
            <Download className="h-6 w-6 text-success" strokeWidth={1.6} />
          ) : (
            <Upload className="h-6 w-6 text-destructive" strokeWidth={1.6} />
          )}
        </div>

        <div className="flex flex-1 items-center justify-between">
          <div className="flex flex-col items-start gap-1">
            <span className="text-xs font-medium tracking-[-0.12px] text-foreground">
              {order.type}
            </span>
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
            <span
              className={cn(
                "text-xs font-semibold tracking-[-0.12px]",
                isPending
                  ? "text-foreground/80"
                  : isDeposit
                    ? "text-success"
                    : "text-destructive",
              )}
            >
              {formatAmount(order.amount)}
            </span>
            <span className="text-[9px] text-muted-foreground">
              {order.status}
            </span>
          </div>
        </div>
      </div>
    );
  }

  const isLong = order.side === "Long";
  const isProfit = order.pnl >= 0;

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
          <span
            className={cn(
              "text-xs font-semibold tracking-[-0.12px]",
              isPending
                ? "text-foreground/80"
                : isProfit
                  ? "text-success"
                  : "text-destructive",
            )}
          >
            {formatAmount(order.pnl)}
          </span>
          <span className="text-[9px] text-muted-foreground">
            {order.status}
          </span>
        </div>
      </div>
    </div>
  );
}
