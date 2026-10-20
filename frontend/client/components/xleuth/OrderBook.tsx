import type { OrderBookRow } from "@/lib/market-data";

function formatAmount(n: number) {
  return n.toLocaleString("en-US");
}

function formatTotal(n: number) {
  return `$${n.toLocaleString("en-US")}`;
}

export function OrderBook(props: {
  priceLabel: string;
  buys?: OrderBookRow[];
  sells?: OrderBookRow[];
}) {
  // Live REST book only; an empty book renders headers with no rows.
  const buys = props.buys ?? [];
  const sells = props.sells ?? [];
  const maxSell = Math.max(...sells.map((r) => r.total), 0) || 1;
  const maxBuy = Math.max(...buys.map((r) => r.total), 0) || 1;

  return (
    <div className="flex w-full flex-col rounded-xl border-[0.4px] border-border bg-card p-3">
      <div className="mb-2 grid grid-cols-3 text-xs text-muted-foreground">
        <span>Price</span>
        <span className="text-center">Amount</span>
        <span className="text-right">Total</span>
      </div>

      <div className="flex flex-col gap-1.5">
        {sells.map((row) => (
          <div
            key={row.price}
            className="relative grid grid-cols-3 py-0.5 text-xs"
          >
            <div
              className="absolute inset-y-0 right-0 bg-destructive/15"
              style={{ width: `${(row.total / maxSell) * 100}%` }}
            />
            <span className="relative z-10 text-destructive">
              {row.price.toFixed(2)}
            </span>
            <span className="relative z-10 text-center text-foreground">
              {formatAmount(row.amount)}
            </span>
            <span className="relative z-10 text-right text-foreground">
              {formatTotal(row.total)}
            </span>
          </div>
        ))}
      </div>

      <div className="my-2 text-center text-base font-semibold text-success">
        {props.priceLabel}
      </div>

      <div className="flex flex-col gap-1.5">
        {buys.map((row) => (
          <div
            key={row.price}
            className="relative grid grid-cols-3 py-0.5 text-xs"
          >
            <div
              className="absolute inset-y-0 right-0 bg-success/15"
              style={{ width: `${(row.total / maxBuy) * 100}%` }}
            />
            <span className="relative z-10 text-success">
              {row.price.toFixed(2)}
            </span>
            <span className="relative z-10 text-center text-foreground">
              {formatAmount(row.amount)}
            </span>
            <span className="relative z-10 text-right text-foreground">
              {formatTotal(row.total)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
