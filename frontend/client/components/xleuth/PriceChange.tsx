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
      <span className="flex items-center gap-1">
        <span className="text-[9px] font-medium leading-[10px] text-warning">
          {DELTA_FALLBACK}
        </span>
        <span className="rounded-lg bg-warning/10 px-2 py-0.5 text-[9px] font-medium leading-[10px] text-warning">
          {DELTA_FALLBACK}
        </span>
      </span>
    );
  }

  const isUp = (abs ?? 0) >= 0;
  const tone = muted ? "text-neutral-400" : isUp ? "text-success" : "text-destructive";
  const toneBg = muted
    ? "bg-neutral-400/20 text-neutral-400"
    : isUp
      ? "bg-success/10 text-success"
      : "bg-destructive/10 text-destructive";

  return (
    <span className="flex items-center gap-1">
      <span className={cn("font-medium leading-[10px]", tone, size === "sm" ? "text-[9px]" : "text-[9px]")}>
        {absText}
      </span>
      <span className={cn("rounded-lg px-2 py-0.5 text-[9px] font-medium leading-[10px]", toneBg)}>
        {pctText}
      </span>
    </span>
  );
}
