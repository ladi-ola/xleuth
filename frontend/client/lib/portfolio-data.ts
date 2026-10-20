// Shared portfolio types. All values render from the API via adapters
// (adaptPosition / adaptOpenOrder / adaptHistoryOrder); this module holds no
// demo data.

export const pnlPeriods = ["1D", "1W", "1M", "YTD", "ALL"] as const;
export type PnlPeriod = (typeof pnlPeriods)[number];

export interface Position {
  id: string;
  symbol: string;
  side: "LONG" | "SHORT";
  leverage: string;
  pnlPct: number;
  pnlAbs: number;
  size: number;
  entry: number;
  current: number;
  margin: number;
  liqPrice: number;
  sl: number;
  tp: number;
  fee: string;
  openedAt: string;
}

export interface OpenOrder {
  id: string;
  side: "Long" | "Short";
  symbol: string;
  size: number;
  entry: number;
  date: string;
  time: string;
  orderType: string;
  status: string;
}

export type HistoryOrder =
  | {
      kind: "trade";
      id: string;
      side: "Long" | "Short";
      symbol: string;
      size: number;
      entry: number;
      date: string;
      time: string;
      pnl: number;
      status: "Completed" | "Pending";
    }
  | {
      kind: "transfer";
      id: string;
      type: "Deposit" | "Withdrawal";
      amount: number;
      date: string;
      time: string;
      status: "Completed" | "Pending";
    };
