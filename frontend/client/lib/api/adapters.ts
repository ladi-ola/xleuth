// Adapters to map API responses to frontend component types

import type {
  BasketInfo,
  BasketPriceResponseWithChange,
  BasketDetail,
  CandlesResponse,
  Candle,
  UserInfo,
  PortfolioSummaryResponse,
  PositionResponse,
  OrderListItem,
  OrderRequest,
  Side,
  TransactionInfo,
  BookSnapshot,
  BookLevel,
} from './schemas';

// ============================================
// Frontend types (from existing components)
// ============================================

export interface FrontendBasket {
  slug: string;
  symbol: string;
  listName: string;
  status: 'active' | 'upcoming' | 'resolved';
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

export interface FrontendPosition {
  id: string;
  symbol: string;
  side: 'LONG' | 'SHORT';
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

export interface FrontendOpenOrder {
  id: string;
  side: 'Long' | 'Short';
  symbol: string;
  size: number;
  entry: number;
  date: string;
  time: string;
  orderType: string;
  status: string;
}

export type FrontendHistoryOrder =
  | {
      kind: 'trade';
      id: string;
      side: 'Long' | 'Short';
      symbol: string;
      size: number;
      entry: number;
      date: string;
      time: string;
      pnl: number;
      status: 'Completed' | 'Pending';
    }
  | {
      kind: 'transfer';
      id: string;
      type: 'Deposit' | 'Withdrawal';
      amount: number;
      date: string;
      time: string;
      status: 'Completed' | 'Pending';
    };

export interface FrontendPortfolioSummary {
  totalBalance: number;
  unrealizedPnl: number;
  freeMargin: number;
  usedMargin: number;
  profitLoss: number;
}

export interface FrontendOrderBookRow {
  price: number;
  amount: number;
  total: number;
}

export interface FrontendCandle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

// ============================================
// Adapter functions
// ============================================

function formatPrice(price: number | null): number {
  return price ?? 0;
}

function formatPriceLabel(price: number | null): string {
  const p = price ?? 0;
  return `${p.toFixed(3)}\u00A2`;
}

function formatTimestamp(ts: string | null): string {
  if (!ts) return 'Unknown';
  try {
    const date = new Date(ts);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    });
  } catch {
    return 'Invalid date';
  }
}

function formatDate(ts: string | null): string {
  if (!ts) return 'Unknown';
  try {
    const date = new Date(ts);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return 'Invalid date';
  }
}

function formatTime(ts: string | null): string {
  if (!ts) return 'Unknown';
  try {
    const date = new Date(ts);
    return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true });
  } catch {
    return 'Invalid time';
  }
}

function mapStatus(apiStatus: string): 'active' | 'upcoming' | 'resolved' {
  switch (apiStatus?.toLowerCase()) {
    case 'active':
      return 'active';
    case 'upcoming':
      return 'upcoming';
    case 'resolved':
      return 'resolved';
    default:
      return 'upcoming';
  }
}

// Map backend basket to frontend basket.
//
// Data-driven: display fields come from API columns (slug, expiry_at,
// total_constituents). Nothing here parses the basket name for month/count —
// the name is a display label only (PLAN.md). Symbol abbreviation is generic
// (first 3 letters of each dash-separated suffix part), not a month list.
export const GLOBAL_MAX_LEVERAGE_DISPLAY = '5x'; // global risk config, not per-basket

export function abbreviateBasketName(name: string): string {
  const parts = name.split('-');
  if (parts.length < 2) return name;
  const head = parts[0];
  const tail = parts.slice(1).map((p) => (p.length > 3 ? p.slice(0, 3) : p));
  return [head, ...tail].join('-');
}

export function adaptBasket(basket: BasketInfo, priceData?: BasketPriceResponseWithChange): FrontendBasket {
  const price = priceData?.scaled_price ?? basket.index_price_scaled ?? basket.index_price ?? 0;
  const changeAbs = priceData?.change_24h_abs ?? null;
  const changePct = priceData?.change_24h_pct ?? null;

  const slug = basket.slug ?? basket.basket_name.toLowerCase().replace(/_/g, '-');
  const expiryIso = basket.expiry_at ?? priceData?.expiry_at ?? null;
  const count = basket.total_constituents ?? priceData?.constituent_count ?? 0;

  return {
    slug,
    symbol: abbreviateBasketName(basket.basket_name),
    listName: basket.basket_name,
    status: mapStatus(basket.status),
    description: `Tracks the ${count} highest-volume markets in this index.`,
    price,
    priceLabel: formatPriceLabel(price),
    changeAbs,
    changePct,
    updatedLabel: priceData?.computed_at ? `Updated ${formatRelativeTime(priceData.computed_at)}` : 'Not yet live',
    resolvesOn: expiryIso ? formatDate(expiryIso) : 'TBD',
    vol: '$---', // Not available from API
    creator: '@xleuth',
    maxLeverage: GLOBAL_MAX_LEVERAGE_DISPLAY,
    resolutionCriteria:
      'If every market in this index resolves YES, index price ends up 100 or 0 if all resolve NO. Otherwise a mix of YES and NO, it ends up the final trading price.',
  };
}

function formatRelativeTime(isoString: string): string {
  try {
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}min${diffMins > 1 ? 's' : ''} ago`;
    if (diffHours < 24) return `${diffHours}hr${diffHours > 1 ? 's' : ''} ago`;
    if (diffDays < 7) return `${diffDays}day${diffDays > 1 ? 's' : ''} ago`;
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch {
    return 'recently';
  }
}

// Map candles
export function adaptCandles(response: CandlesResponse): FrontendCandle[] {
  return response.candles.map((c) => ({
    time: c.time,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  }));
}

// Map order book
export function adaptOrderBook(snapshot: BookSnapshot): { buys: FrontendOrderBookRow[]; sells: FrontendOrderBookRow[] } {
  const buys: FrontendOrderBookRow[] = snapshot.bids.map((level) => ({
    price: level.price,
    amount: level.size,
    total: level.price * level.size,
  }));

  const sells: FrontendOrderBookRow[] = snapshot.asks.map((level) => ({
    price: level.price,
    amount: level.size,
    total: level.price * level.size,
  }));

  return { buys, sells };
}

// Map positions
export function adaptPosition(pos: PositionResponse): FrontendPosition {
  const isLong = pos.side === 'buy' || pos.side === 'long';

  return {
    id: pos.position_id,
    symbol: abbreviateBasketName(pos.basket_name),
    side: isLong ? 'LONG' : 'SHORT',
    leverage: `${pos.leverage}x Leverage`,
    pnlPct: pos.unrealized_pnl_pct,
    pnlAbs: pos.unrealized_pnl_abs,
    size: pos.size,
    entry: pos.entry_price,
    current: pos.mark_price,
    margin: pos.margin_usdc,
    liqPrice: pos.liquidation_price ?? 0,
    sl: pos.stop_loss_price ?? 0,
    tp: pos.take_profit_price ?? 0,
    fee: pos.fee_paid ? `${pos.fee_paid}%` : '—',
    openedAt: formatTimestamp(pos.opened_at),
  };
}

// Map orders
export function adaptOpenOrder(order: OrderListItem): FrontendOpenOrder {
  const isLong = order.side === 'buy';

  return {
    id: order.order_id,
    side: isLong ? 'Long' : 'Short',
    symbol: abbreviateBasketName(order.basket_name),
    size: order.size,
    entry: order.price ?? 0,
    date: formatDate(order.created_at),
    time: formatTime(order.created_at),
    orderType: order.order_type.charAt(0).toUpperCase() + order.order_type.slice(1),
    status: order.status.charAt(0).toUpperCase() + order.status.slice(1).replace('_', ' '),
  };
}

export function adaptHistoryOrder(order: OrderListItem): FrontendHistoryOrder {
  const isLong = order.side === 'buy';
  const isFilled = order.status === 'filled';
  const pnl = order.average_fill_price && order.filled_size > 0
    ? (order.average_fill_price - (order.price || order.average_fill_price)) * order.filled_size * (isLong ? 1 : -1)
    : 0;

  return {
    kind: 'trade',
    id: order.order_id,
    side: isLong ? 'Long' : 'Short',
    symbol: abbreviateBasketName(order.basket_name),
    size: order.filled_size,
    entry: order.average_fill_price ?? order.price ?? 0,
    date: formatDate(order.updated_at || order.created_at),
    time: formatTime(order.updated_at || order.created_at),
    pnl,
    status: isFilled ? 'Completed' : 'Pending',
  };
}

export function adaptTransaction(tx: TransactionInfo): FrontendHistoryOrder {
  const isDeposit = tx.tx_type === 'deposit' || tx.tx_type === 'Deposit';
  const isWithdrawal = tx.tx_type === 'withdrawal' || tx.tx_type === 'Withdrawal';

  if (isDeposit || isWithdrawal) {
    return {
      kind: 'transfer',
      id: String(tx.id ?? tx.tx_hash ?? Math.random()),
      type: isDeposit ? 'Deposit' : 'Withdrawal',
      amount: isDeposit ? tx.amount : -tx.amount,
      date: formatDate(tx.timestamp),
      time: formatTime(tx.timestamp),
      status: tx.tx_hash ? 'Completed' : 'Pending',
    };
  }

  // For trades, fall back to order format
  return {
    kind: 'trade',
    id: String(tx.id ?? tx.tx_hash ?? Math.random()),
    side: 'Long', // Can't determine from transaction alone
    symbol: 'UNKNOWN',
    size: 0,
    entry: 0,
    date: formatDate(tx.timestamp),
    time: formatTime(tx.timestamp),
    pnl: 0,
    status: 'Completed',
  };
}

// Map portfolio summary
export function adaptPortfolioSummary(summary: PortfolioSummaryResponse): FrontendPortfolioSummary {
  return {
    totalBalance: summary.total_balance,
    unrealizedPnl: summary.unrealized_pnl,
    freeMargin: summary.free_margin,
    usedMargin: summary.used_margin,
    profitLoss: summary.realized_pnl + summary.unrealized_pnl,
  };
}

// Map account info
export function adaptAccount(user: UserInfo): { address: string; alias: string | null; balance: number } {
  return {
    address: user.wallet_address,
    alias: user.alias,
    balance: user.balance,
  };
}

export type TradeOrderType = 'market' | 'limit' | 'stop';

// Build an order request from the trade modal's USDC-notional input. API size
// is in index units (contracts) with notional ~= indexPrice x size, so
// size = notional / indexPrice for every order type. Limit orders additionally
// carry the resting price; stop orders carry the trigger price plus the same
// slippage guard as market orders. The server is the authority on min size,
// tick, margin and slippage: this only translates units, it never validates.
export function buildOrder(args: {
  basketName: string;
  side: 'buy' | 'sell';
  orderType: TradeOrderType;
  notionalUsdc: number;
  indexPrice: number;
  leverage: number;
  slippageBps?: number;
  limitPrice?: number;
  triggerPrice?: number;
}): OrderRequest {
  const side: Side = args.side;
  // Round the derived size so a notional that should produce a whole number
  // doesn't send e.g. 9.999999999999998 from floating-point division. Six
  // decimals is enough to preserve any meaningful notional precision.
  const size =
    args.indexPrice > 0 ? Number((args.notionalUsdc / args.indexPrice).toFixed(6)) : 0;
  const base = {
    basket_name: args.basketName,
    side,
    size,
    leverage: args.leverage,
  };
  if (args.orderType === 'limit') {
    return { ...base, order_type: 'limit', price: args.limitPrice ?? null };
  }
  if (args.orderType === 'stop') {
    return {
      ...base,
      order_type: 'stop',
      trigger_price: args.triggerPrice ?? null,
      max_slippage_bps: Math.floor(args.slippageBps ?? 0),
    };
  }
  return {
    ...base,
    order_type: 'market',
    max_slippage_bps: Math.floor(args.slippageBps ?? 0),
  };
}

// Build a market (FOK + slippage guard) order request. Kept as a named
// convenience wrapper around buildOrder for existing callers/tests.
export function buildMarketOrder(args: {
  basketName: string;
  side: 'buy' | 'sell';
  notionalUsdc: number;
  price: number;
  leverage: number;
  slippageBps: number;
}): OrderRequest {
  return buildOrder({
    basketName: args.basketName,
    side: args.side,
    orderType: 'market',
    notionalUsdc: args.notionalUsdc,
    indexPrice: args.price,
    leverage: args.leverage,
    slippageBps: args.slippageBps,
  });
}