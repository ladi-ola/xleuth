import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTheme } from "next-themes";
import {
  createChart,
  ColorType,
  LineSeries,
  CandlestickSeries,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { cn } from "@/lib/utils";
import { EmptyState } from "./EmptyState";

const TIMEFRAMES = ["1H", "1D", "1W", "1M"] as const;
type Timeframe = (typeof TIMEFRAMES)[number];

/** Resolve a theme token (stored as HSL channels) into a chart CSS color. */
function themeColor(name: string, fallback: string, alpha?: number) {
  if (typeof document === "undefined") return fallback;
  const raw = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  if (!raw) return fallback;
  return alpha === undefined ? `hsl(${raw})` : `hsl(${raw} / ${alpha})`;
}

export function PriceChart(props: {
  candles?: {
    time: number;
    open: number;
    high: number;
    low: number;
    close: number;
  }[];
  /** Optional desktop-only controls rendered at the bottom of the chart card. */
  footer?: ReactNode;
}) {
  const liveCandles = props.candles ?? [];
  const hasData = liveCandles.length > 0;
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<
    ISeriesApi<"Line"> | ISeriesApi<"Candlestick"> | null
  >(null);
  const [chartType, setChartType] = useState<"line" | "candlestick">("line");
  const [timeframe, setTimeframe] = useState<Timeframe>("1D");
  const { resolvedTheme } = useTheme();

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: themeColor("--muted-foreground", "#5a5a63"),
        fontFamily: "Poppins, -apple-system, Roboto, Helvetica, sans-serif",
        fontSize: 11,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: themeColor("--border", "#d4d4d8", 0.55) },
        horzLines: { color: themeColor("--border", "#d4d4d8", 0.55) },
      },
      rightPriceScale: {
        borderVisible: false,
      },
      timeScale: {
        borderVisible: false,
        timeVisible: true,
      },
      crosshair: {
        vertLine: {
          color: themeColor("--muted-foreground", "#5a5a63", 0.45),
          labelBackgroundColor: themeColor("--accent", "#f4eaf5"),
        },
        horzLine: {
          color: themeColor("--muted-foreground", "#5a5a63", 0.45),
          labelBackgroundColor: themeColor("--accent", "#f4eaf5"),
        },
      },
      autoSize: true,
    });

    chartRef.current = chart;

    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [resolvedTheme]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    if (seriesRef.current) {
      chart.removeSeries(seriesRef.current);
      seriesRef.current = null;
    }

    // Live candles only. With no data yet the chart renders its empty grid
    // rather than fabricated prices.
    const candles = liveCandles;

    if (chartType === "line") {
      const series = chart.addSeries(LineSeries, {
        color: themeColor("--primary", "#7a3e86"),
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
      });
      series.setData(
        candles.map((c) => ({
          time: c.time as UTCTimestamp,
          value: c.close,
        })),
      );
      seriesRef.current = series;
    } else {
      const up = themeColor("--success", "#157347");
      const down = themeColor("--destructive", "#c01230");
      const series = chart.addSeries(CandlestickSeries, {
        upColor: up,
        downColor: down,
        borderVisible: false,
        wickUpColor: up,
        wickDownColor: down,
      });
      series.setData(
        candles.map((c) => ({
          time: c.time as UTCTimestamp,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        })),
      );
      seriesRef.current = series;
    }

    chart.timeScale().fitContent();
  }, [chartType, timeframe, liveCandles, resolvedTheme]);

  return (
    <div className="flex w-full flex-col gap-3 rounded-xl border-[0.4px] border-border bg-card p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1 rounded-lg border-[0.4px] border-border bg-muted p-0.5">
          {(["line", "candlestick"] as const).map((type) => (
            <button
              key={type}
              onClick={() => setChartType(type)}
              className={cn(
                "rounded-md px-2 py-1 text-[9px] font-medium uppercase tracking-wide",
                chartType === type
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground",
              )}
            >
              {type === "line" ? "Line" : "Candles"}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1 rounded-lg border-[0.4px] border-border bg-muted p-0.5">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={cn(
                "rounded-md px-2 py-1 text-[9px] font-medium",
                timeframe === tf
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground",
              )}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>
      <div className="relative h-[338px] w-full md:h-[420px] lg:h-[520px]">
        {/* The chart container stays mounted (sized) so the chart instance is
            ready; it is only hidden while there is no data to plot. */}
        <div
          ref={containerRef}
          className={cn("h-full w-full", !hasData && "invisible")}
        />
        {!hasData && (
          <div className="absolute inset-0 flex items-center justify-center">
            <EmptyState
              title="No data yet"
              caption="Price history will appear once the index is live"
            />
          </div>
        )}
      </div>
      {props.footer ? (
        <div className="border-t-[0.4px] border-border pt-3">
          {props.footer}
        </div>
      ) : null}
    </div>
  );
}
