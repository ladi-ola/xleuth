import { useEffect, useRef, useState } from "react";
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

const TIMEFRAMES = ["1H", "1D", "1W", "1M"] as const;
type Timeframe = (typeof TIMEFRAMES)[number];

export function PriceChart(props: {
  candles?: { time: number; open: number; high: number; low: number; close: number }[];
}) {
  const liveCandles = props.candles ?? [];
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Line"> | ISeriesApi<"Candlestick"> | null>(
    null,
  );
  const [chartType, setChartType] = useState<"line" | "candlestick">("line");
  const [timeframe, setTimeframe] = useState<Timeframe>("1D");

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "rgba(255, 255, 255, 0.8)",
        fontFamily: "Poppins, -apple-system, Roboto, Helvetica, sans-serif",
        fontSize: 11,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: "rgba(64, 64, 64, 0.4)" },
        horzLines: { color: "rgba(64, 64, 64, 0.4)" },
      },
      rightPriceScale: {
        borderVisible: false,
      },
      timeScale: {
        borderVisible: false,
        timeVisible: true,
      },
      crosshair: {
        vertLine: { color: "#404040", labelBackgroundColor: "#240D28" },
        horzLine: { color: "#404040", labelBackgroundColor: "#240D28" },
      },
      autoSize: true,
    });

    chartRef.current = chart;

    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

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
        color: "#94679A",
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
      const series = chart.addSeries(CandlestickSeries, {
        upColor: "#1FC16B",
        downColor: "#FB3748",
        borderVisible: false,
        wickUpColor: "#1FC16B",
        wickDownColor: "#FB3748",
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
  }, [chartType, timeframe, liveCandles]);

  return (
    <div className="flex w-full flex-col gap-3 rounded-xl border-[0.4px] border-neutral-600 bg-neutral-900 p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1 rounded-lg border-[0.4px] border-neutral-600 bg-neutral-800 p-0.5">
          {(["line", "candlestick"] as const).map((type) => (
            <button
              key={type}
              onClick={() => setChartType(type)}
              className={cn(
                "rounded-md px-2 py-1 text-[9px] font-medium uppercase tracking-wide",
                chartType === type
                  ? "bg-primary-dark text-neutral-50"
                  : "text-neutral-400",
              )}
            >
              {type === "line" ? "Line" : "Candles"}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1 rounded-lg border-[0.4px] border-neutral-600 bg-neutral-800 p-0.5">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={cn(
                "rounded-md px-2 py-1 text-[9px] font-medium",
                timeframe === tf
                  ? "bg-primary-dark text-neutral-50"
                  : "text-neutral-400",
              )}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>
      <div ref={containerRef} className="h-[338px] w-full" />
    </div>
  );
}
