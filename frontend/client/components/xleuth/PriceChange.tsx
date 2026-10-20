import { cn } from "@/lib/utils";
import { DELTA_FALLBACK, formatDelta, formatPercentDelta } from "@/lib/format";

export function PriceChange({
  abs,
  pct,
  size = "sm",
  muted = false,
}: {
  abs: number | null;
  pct: number | null;
  size?: "sm" | "xs";
  muted?: boolean;
}) {
  const absText = formatDelta(abs);
  const pctText = formatPercentDelta(pct);

  if (absText === DELTA_FALLBACK || pctText === DELTA_FALLBACK) {
    return (
      <span
        className="text-[9px] font-medium leading-[10px] text-muted-foreground"
        title="24h change not available"
      >
        {DELTA_FALLBACK}
      </span>
    );
  }

  const isUp = (abs ?? 0) >= 0;
  const tone = muted
    ? "text-muted-foreground"
    : isUp
      ? "text-success"
      : "text-destructive";
  const toneBg = muted
    ? "bg-muted text-muted-foreground"
    : isUp
      ? "bg-success/10 text-success"
      : "bg-destructive/10 text-destructive";

  return (
    <span className="flex items-center gap-1">
      <span
        className={cn(
          "font-medium leading-[10px]",
          tone,
          size === "sm" ? "text-[9px]" : "text-[9px]",
        )}
      >
        {absText}
      </span>
      <span
        className={cn(
          "rounded-lg px-2 py-0.5 text-[9px] font-medium leading-[10px]",
          toneBg,
        )}
      >
        {pctText}
      </span>
    </span>
  );
}
