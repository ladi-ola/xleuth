export interface OrderBookRow {
  price: number;
  amount: number;
  total: number;
}

export type BasketStatus = "active" | "upcoming" | "resolved";

export interface Basket {
  slug: string;
  symbol: string;
  listName: string;
  status: BasketStatus;
  description: string;
  price: number;
  priceLabel: string;
  changeAbs: number | null;
  changePct: number | null;
  updatedLabel: string;
  resolvesOn: string;
  vol: string;
  creator: string;
  maxLeverage: string;
  resolutionCriteria: string;
}

export const baskets: Basket[] = [
  {
    slug: "top20-september",
    symbol: "TOP20-SEPT",
    listName: "TOP20-SEPTEMBER",
    status: "active",
    description:
      "Tracks the 20 highest-volume non-sport market that resolves in September.",
    price: 43.657,
    priceLabel: "43.657\u00A2",
    changeAbs: 2.38,
    changePct: 1.7,
    updatedLabel: "Updated 24mins ago",
    resolvesOn: "Sept 30, 2026",
    vol: "$1.83M",
    creator: "@xleuth",
    maxLeverage: "5x",
    resolutionCriteria:
      "If every markets in this index resolve YES, index price ends up 100 or 0 if all resolve NO. Otherwise a mix of YES and NO, it ends up the final trading price.",
  },
  {
    slug: "top20-q4",
    symbol: "TOP20-Q4",
    listName: "TOP20-Q4",
    status: "active",
    description:
      "Tracks the 20 highest-volume non-sport market that resolves in Q4.",
    price: 71.833,
    priceLabel: "71.833\u00A2",
    changeAbs: 0.89,
    changePct: 0.37,
    updatedLabel: "Updated 24mins ago",
    resolvesOn: "Dec 31, 2026",
    vol: "$4.77M",
    creator: "@xleuth",
    maxLeverage: "5x",
    resolutionCriteria:
      "If every markets in this index resolve YES, index price ends up 100 or 0 if all resolve NO. Otherwise a mix of YES and NO, it ends up the final trading price.",
  },
  {
    slug: "top20-october",
    symbol: "TOP20-OCT",
    listName: "TOP20-OCTOBER",
    status: "active",
    description:
      "Tracks the 20 highest-volume non-sport market that resolves in October.",
    price: 23.91,
    priceLabel: "23.91\u00A2",
    changeAbs: 3.17,
    changePct: 1.9,
    updatedLabel: "Updated 24mins ago",
    resolvesOn: "Sept 30, 2026",
    vol: "$127.2K",
    creator: "@xleuth",
    maxLeverage: "5x",
    resolutionCriteria:
      "If every markets in this index resolve YES, index price ends up 100 or 0 if all resolve NO. Otherwise a mix of YES and NO, it ends up the final trading price.",
  },
  {
    slug: "top20-december",
    symbol: "TOP20-DEC",
    listName: "TOP20-DECEMBER",
    status: "upcoming",
    description:
      "Tracks the 20 highest-volume non-sport market that resolves in December.",
    price: 0,
    priceLabel: "0.00\u00A2",
    changeAbs: null,
    changePct: null,
    updatedLabel: "Not yet live",
    resolvesOn: "Dec 31, 2026",
    vol: "$---",
    creator: "@xleuth",
    maxLeverage: "5x",
    resolutionCriteria:
      "If every markets in this index resolve YES, index price ends up 100 or 0 if all resolve NO. Otherwise a mix of YES and NO, it ends up the final trading price.",
  },
  {
    slug: "top20-august",
    symbol: "TOP20-AUG",
    listName: "TOP20-AUGUST",
    status: "resolved",
    description:
      "Tracks the 20 highest-volume non-sport market that resolves in August.",
    price: 89.47,
    priceLabel: "89.47\u00A2",
    changeAbs: 0,
    changePct: 0,
    updatedLabel: "Resolved",
    resolvesOn: "Aug 31, 2026",
    vol: "$975.2K",
    creator: "@xleuth",
    maxLeverage: "5x",
    resolutionCriteria:
      "If every markets in this index resolve YES, index price ends up 100 or 0 if all resolve NO. Otherwise a mix of YES and NO, it ends up the final trading price.",
  },
];

export function getBasket(slug: string | undefined): Basket {
  return baskets.find((b) => b.slug === slug) ?? baskets[0];
}

export const constituents: string[] = [
  "Next prime minister of Ethiopia",
  "Netanyahu out by September 30",
  "Fed decision in September?",
  "Will the US confirm that aliens exist before September 30",
  "What price will Bitcoin hit in September 2026",
  "Brazil Presidential Election",
  "California Governorship Election winner",
  "US x Iran Effective Ceasefire begins by September 30",
  "Trump out as President by September 30?",
  "Best Chinese AI Company end of September",
  "Will China invade Taiwan by September 30, 2026?",
  "What price will XRP hit in September?",
  "Crude Oil all time high by September 30",
  "Will OpenAI's valuation hit $1T by September 30?",
  "Bank of Russia decision in September?",
  "Fed rate hike by September Meeting",
  "Israel closes its airspace by September 30",
  "Israel x Iran ceasefire continues through September 30",
  "Strait of Hormuz traffic returns to normal by September 30?",
];

export const orderBookSells: OrderBookRow[] = [
  { price: 48.11, amount: 1025, total: 493127 },
  { price: 47.89, amount: 128, total: 61300 },
  { price: 45.24, amount: 50, total: 22620 },
  { price: 44.52, amount: 65, total: 28938 },
  { price: 43.89, amount: 217, total: 95241 },
];

export const orderBookBuys: OrderBookRow[] = [
  { price: 43.53, amount: 97, total: 42224 },
  { price: 43.49, amount: 580, total: 250224 },
  { price: 43.41, amount: 650, total: 280216 },
  { price: 42.9, amount: 180, total: 77220 },
  { price: 42.31, amount: 245, total: 103660 },
  { price: 41.86, amount: 428, total: 179160 },
];

export const currentPosition = {
  side: "Long" as const,
  size: 183,
  entryPrice: 65.26,
  pnl: 123.65,
};

// TODO: replace with live index price feed (websocket / REST polling of the on-chain index oracle).
export function generateMockCandles(count = 180, basePrice = 40) {
  const candles: { time: number; open: number; high: number; low: number; close: number }[] = [];
  let last = basePrice + Math.random() * 4;
  const now = Math.floor(Date.now() / 1000);
  const step = 60 * 15; // 15 min candles
  for (let i = count; i >= 0; i--) {
    const open = last;
    const drift = (Math.random() - 0.48) * 2.4;
    const close = Math.max(2, Math.min(98, open + drift));
    const high = Math.max(open, close) + Math.random() * 1.2;
    const low = Math.min(open, close) - Math.random() * 1.2;
    candles.push({
      time: now - i * step,
      open,
      high,
      low,
      close,
    });
    last = close;
  }
  return candles;
}
