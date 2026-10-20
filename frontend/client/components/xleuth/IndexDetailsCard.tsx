import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Basket } from "@/lib/market-data";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-xs text-foreground">{value}</span>
    </div>
  );
}

export function IndexDetailsCard({
  basket,
  constituents: liveConstituents,
}: {
  basket: Basket;
  constituents?: string[];
}) {
  const [constituentsOpen, setConstituentsOpen] = useState(false);
  const [criteriaOpen, setCriteriaOpen] = useState(false);

  // Live constituent list only; no sample data.
  const constituents = liveConstituents ?? [];

  return (
    <div className="flex w-full flex-col gap-3 rounded-xl border-[0.4px] border-border bg-card p-3">
      <div className="flex flex-col gap-2">
        <span className="text-sm font-medium text-foreground">
          Index details
        </span>
        <Row label="Resolution" value={basket.resolvesOn} />
        <Row label="Creator" value={basket.creator} />
        <Row label="Vol. 24h" value={basket.vol} />
        <Row label="Max Leverage" value={basket.maxLeverage} />
      </div>

      <div className="flex flex-col gap-2">
        <button
          onClick={() => setConstituentsOpen((v) => !v)}
          className="flex items-center gap-1"
        >
          <span className="text-sm font-medium text-foreground">
            Constituents
          </span>
          <ChevronDown
            className={cn(
              "h-4 w-4 text-foreground transition-transform",
              constituentsOpen && "rotate-180",
            )}
          />
        </button>
        {constituentsOpen && (
          <div className="flex flex-col gap-1.5">
            {constituents.length === 0 ? (
              <span className="text-[9px] leading-[10px] text-muted-foreground">
                No data yet
              </span>
            ) : (
              constituents.map((market) => (
                <span
                  key={market}
                  className="text-[9px] leading-[10px] text-muted-foreground"
                >
                  {market}
                </span>
              ))
            )}
          </div>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <button
          onClick={() => setCriteriaOpen((v) => !v)}
          className="flex items-center gap-1"
        >
          <span className="text-xs font-medium text-foreground">
            View resolution criteria
          </span>
          <ChevronDown
            className={cn(
              "h-4 w-4 text-foreground transition-transform",
              criteriaOpen && "rotate-180",
            )}
          />
        </button>
        {criteriaOpen && (
          <p className="text-justify text-[9px] leading-[10px] text-muted-foreground">
            {basket.resolutionCriteria}
          </p>
        )}
      </div>
    </div>
  );
}
