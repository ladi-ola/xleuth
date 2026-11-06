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
  tradeable: boolean;
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

const PLACEHOLDER_BASKET: Basket = {
  slug: "placeholder",
  symbol: "--",
  listName: "Loading...",
  status: "upcoming",
  tradeable: false,
  description: "Basket data loads from the API.",
  price: 0,
  priceLabel: "0.000",
  changeAbs: null,
  changePct: null,
  updatedLabel: "Not yet live",
  resolvesOn: "TBD",
  vol: "—",
  creator: "@xleuth",
  maxLeverage: "5x",
  resolutionCriteria:
    "If every market in this index resolves YES, index price ends up 100 or 0 if all resolve NO. Otherwise a mix of YES and NO, it ends up the final trading price.",
};

/**
 * Fallback used by UI states that render before any basket is available
 * (e.g. the Portfolio sign-in sheet). Baskets themselves are data, never
 * config — they come from GET /baskets via adaptBasket().
 */
export function getBasket(_slug: string | undefined): Basket {
  return PLACEHOLDER_BASKET;
}
