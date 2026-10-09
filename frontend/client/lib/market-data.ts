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

/**
 * DEPRECATED basket fixtures (PLAN.md: baskets are data, not config).
 *
 * Explore/Markets pages already render from GET /baskets via adaptBasket().
 * This module now only keeps type shapes + a generic placeholder for offline
 * UI states (e.g. Portfolio sign-in sheet before data loads). Do NOT add
 * per-basket entries here - create baskets through the admin CLI.
 */

export const baskets: Basket[] = [];

const PLACEHOLDER_BASKET: Basket = {
  slug: "placeholder",
  symbol: "--",
  listName: "Loading...",
  status: "upcoming",
  description: "Basket data loads from the API.",
  price: 0,
  priceLabel: "0.000",
  changeAbs: null,
  changePct: null,
  updatedLabel: "Not yet live",
  resolvesOn: "TBD",
  vol: "$---",
  creator: "@xleuth",
  maxLeverage: "5x",
  resolutionCriteria:
    "If every markets in this index resolve YES, index price ends up 100 or 0 if all resolve NO. Otherwise a mix of YES and NO, it ends up the final trading price.",
};

export function getBasket(slug: string | undefined): Basket {
  return baskets.find((b) => b.slug === slug) ?? PLACEHOLDER_BASKET;
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
