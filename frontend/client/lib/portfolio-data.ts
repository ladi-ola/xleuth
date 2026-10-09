// TODO: replace with live portfolio data (websocket / REST polling of the user's on-chain positions).
export const portfolioSummary = {
  totalBalance: 1000.0,
  unrealizedPnl: 1250.0,
  freeMargin: 550.0,
  usedMargin: 450.0,
  profitLoss: 8500.0,
};

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

export const positions: Position[] = [
  {
    id: "pos-1",
    symbol: "TOP20-SEPT",
    side: "LONG",
    leverage: "2x Leverage",
    pnlPct: -17.1,
    pnlAbs: -310.65,
    size: 410,
    entry: 32.74,
    current: 28.76,
    margin: 450,
    liqPrice: 20.54,
    sl: 23.5,
    tp: 65.43,
    fee: "0.5%",
    openedAt: "09-07-2026 13:54:17",
  },
  {
    id: "pos-2",
    symbol: "TOP20-SEPT",
    side: "SHORT",
    leverage: "2x Leverage",
    pnlPct: 17.1,
    pnlAbs: 565.7,
    size: 410,
    entry: 32.74,
    current: 28.76,
    margin: 450,
    liqPrice: 20.54,
    sl: 23.5,
    tp: 65.43,
    fee: "0.5%",
    openedAt: "09-07-2026 13:54:17",
  },
];

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

export const openOrders: OpenOrder[] = [
  {
    id: "open-1",
    side: "Long",
    symbol: "TOP20-SEPT",
    size: 250,
    entry: 34.72,
    date: "Sept 5, 2026",
    time: "19:43:22",
    orderType: "Limit",
    status: "Pending",
  },
  {
    id: "open-2",
    side: "Short",
    symbol: "TOP20-SEPT",
    size: 250,
    entry: 34.72,
    date: "Sept 5, 2026",
    time: "19:43:22",
    orderType: "Limit",
    status: "Pending",
  },
];

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

export const historyOrders: HistoryOrder[] = [
  {
    kind: "trade",
    id: "history-1",
    side: "Long",
    symbol: "TOP20-SEPT",
    size: 250,
    entry: 34.72,
    date: "Sept 5, 2026",
    time: "19:43:22",
    pnl: 1550,
    status: "Completed",
  },
  {
    kind: "trade",
    id: "history-2",
    side: "Long",
    symbol: "TOP20-SEPT",
    size: 250,
    entry: 34.72,
    date: "Sept 5, 2026",
    time: "19:43:22",
    pnl: -350,
    status: "Completed",
  },
  {
    kind: "trade",
    id: "history-3",
    side: "Short",
    symbol: "TOP20-SEPT",
    size: 250,
    entry: 34.72,
    date: "Sept 5, 2026",
    time: "19:43:22",
    pnl: 1550,
    status: "Completed",
  },
  {
    kind: "trade",
    id: "history-4",
    side: "Short",
    symbol: "TOP20-SEPT",
    size: 250,
    entry: 34.72,
    date: "Sept 5, 2026",
    time: "19:43:22",
    pnl: -350,
    status: "Completed",
  },
  {
    kind: "transfer",
    id: "history-5",
    type: "Deposit",
    amount: 1000,
    date: "Sept 5, 2026",
    time: "19:43:22",
    status: "Completed",
  },
  {
    kind: "transfer",
    id: "history-6",
    type: "Withdrawal",
    amount: -500,
    date: "Sept 5, 2026",
    time: "19:43:22",
    status: "Completed",
  },
  {
    kind: "transfer",
    id: "history-7",
    type: "Deposit",
    amount: 1000,
    date: "Sept 5, 2026",
    time: "19:43:22",
    status: "Pending",
  },
  {
    kind: "transfer",
    id: "history-8",
    type: "Withdrawal",
    amount: -500,
    date: "Sept 5, 2026",
    time: "19:43:22",
    status: "Pending",
  },
];
