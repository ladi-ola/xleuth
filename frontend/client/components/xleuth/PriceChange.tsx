import { cn } from "@/lib/utils";

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
  if (abs === null || pct === null) {
    return (
      <span className="flex items-center gap-1">
        <span className="text-[9px] font-medium leading-[10px] text-warning">---</span>
        <span className="rounded-lg bg-warning/10 px-2 py-0.5 text-[9px] font-medium leading-[10px] text-warning">
          ---
        </span>
      </span>
    );
  }

  const isUp = abs >= 0;
  const tone = muted ? "text-neutral-400" : isUp ? "text-success" : "text-destructive";
  const toneBg = muted
    ? "bg-neutral-400/20 text-neutral-400"
    : isUp
      ? "bg-success/10 text-success"
      : "bg-destructive/10 text-destructive";

  return (
    <span className="flex items-center gap-1">
      <span className={cn("font-medium leading-[10px]", tone, size === "sm" ? "text-[9px]" : "text-[9px]")}>
        {isUp ? "+" : ""}
        {abs}
      </span>
      <span className={cn("rounded-lg px-2 py-0.5 text-[9px] font-medium leading-[10px]", toneBg)}>
        {isUp ? "+" : ""}
        {Number.isInteger(pct) ? pct.toFixed(1) : pct}%
      </span>
    </span>
  );
}
