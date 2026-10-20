import { cn } from "@/lib/utils";
import { formatPercentDelta } from "@/lib/format";
import type { Position } from "@/lib/portfolio-data";

function Cell({
  label,
  value,
  align = "start",
}: {
  label: string;
  value: string;
  align?: "start" | "center" | "end";
}) {
  return (
    <div
      className={cn(
        "flex flex-1 flex-col justify-start gap-1",
        align === "end"
          ? "items-end"
          : align === "center"
            ? "items-center"
            : "items-start",
      )}
    >
      <span className="text-[9px] text-muted-foreground">{label}</span>
      <span className="text-xs font-medium text-foreground">{value}</span>
    </div>
  );
}

export function PositionCard({ position }: { position: Position }) {
  const isLong = position.side === "LONG";
  const isProfit = position.pnlAbs >= 0;

  return (
    <div className="flex w-full flex-col items-center gap-4 rounded-2xl border-[0.4px] border-border bg-card p-4">
      <div className="flex w-full items-start justify-between">
        <div className="flex flex-col justify-between gap-1">
          <span className="text-sm font-semibold tracking-[-0.16px] text-foreground">
            {position.symbol}
          </span>
          <div className="flex items-center gap-1">
            <span
              className={cn(
                "rounded-lg px-2 py-0.5 text-[9px] font-medium",
                isLong
                  ? "bg-success/10 text-success"
                  : "bg-destructive/10 text-destructive",
              )}
            >
              {position.side}
            </span>
            <span className="text-[10px] text-foreground/80">
              {position.leverage}
            </span>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className="text-[9px] text-muted-foreground">
            Unrealized PnL
          </span>
          <span
            className={cn(
              "text-sm font-semibold",
              isProfit ? "text-success" : "text-destructive",
            )}
          >
            {formatPercentDelta(position.pnlPct)} {isProfit ? "+" : "-"}$
            {Math.abs(position.pnlAbs).toFixed(2)}
          </span>
        </div>
      </div>

      <div className="flex w-full items-start justify-between">
        <Cell label="Size" value={String(position.size)} />
        <Cell label="Entry" value={position.entry.toFixed(2)} align="center" />
        <Cell
          label="Current"
          value={position.current.toFixed(2)}
          align="center"
        />
        <Cell label="Margin" value={String(position.margin)} align="end" />
      </div>
      <div className="flex w-full items-start justify-between">
        <Cell label="Liq. Price" value={position.liqPrice.toFixed(2)} />
        <Cell label="S/L" value={position.sl.toFixed(2)} align="center" />
        <Cell label="T/P" value={position.tp.toFixed(2)} align="center" />
        <Cell label="Fee" value={position.fee} align="end" />
      </div>

      <div className="flex w-full justify-end">
        <span className="text-[9px] text-muted-foreground">
          Open {position.openedAt}
        </span>
      </div>
    </div>
  );
}
