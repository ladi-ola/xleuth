// Generated from docs/openapi/xleuth-api.json and docs/openapi/xleuth-matching.json
// DO NOT EDIT MANUALLY - regenerate from OpenAPI specs when they change

// ============================================
// Backend API (port 8000) - Baskets
// ============================================

export interface BasketInfo {
  basket_name: string;
  total_constituents: number;
  index_price: number | null;
  index_price_scaled: number | null;
  computed_at: string | null;
  status: string;
  is_tradeable: boolean;
  slug?: string | null;
  expiry_at?: string | null;
  onchain_index_id?: string | null;
}

export interface BasketListResponse {
  baskets: BasketInfo[];
}

export interface BasketPriceResponseWithChange {
  basket_name: string;
  index_price: number | null;
  scaled_price: number | null;
  computed_at: string | null;
  constituent_count: number | null;
  status: string;
  is_tradeable: boolean;
  change_24h_abs: number | null;
  change_24h_pct: number | null;
  slug?: string | null;
  expiry_at?: string | null;
  onchain_index_id?: string | null;
}

export interface BasketHistoryResponse {
  basket_name: string;
  prices: PricePoint[];
}

export interface PricePoint {
  ts: string;
  basket_name: string;
  index_price: number | null;
  scaled_price: number | null;
  constituent_count: number | null;
}

export interface ConstituentMarket {
  condition_id: string | null;
  clob_token_id: string | null;
  event_id: string | null;
  question: string | null;
  end_date: string | null;
  price: number | null;
  volume: number;
  price_source: string | null;
  sub_markets: ConstituentSubMarket[] | null;
  sub_market_count: number | null;
  market_id: string | null;
}

export interface ConstituentSubMarket {
  condition_id: string | null;
  clob_token_id: string | null;
  price: number | null;
  volume: number;
}

export interface BasketDetail {
  basket_name: string;
  total_constituents: number;
  index_price: number | null;
  index_price_scaled: number | null;
  computed_at: string | null;
  status: string;
  is_tradeable: boolean;
  constituents: ConstituentMarket[];
  markets_filtered_out: number;
  excluded_markets: Record<string, unknown>[];
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface CandlesResponse {
  basket_name: string;
  interval: string;
  candles: Candle[];
}

// ============================================
// Backend API - Auth
// ============================================

export interface DynamicVerifyRequest {
  token: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in_minutes: number;
}

// ============================================
// Backend API - Accounts
// ============================================

export interface UserInfo {
  wallet_address: string;
  alias: string | null;
  balance: number;
  realized_pnl: number;
  unrealized_pnl: number;
  created_at: string | null;
}

export interface TransactionInfo {
  id: number | null;
  wallet_address: string;
  tx_type: string;
  amount: number;
  tx_hash: string | null;
  timestamp: string | null;
  related_position_id: number | null;
}

export interface TransactionHistoryResponse {
  wallet_address: string;
  transactions: TransactionInfo[];
}

export interface PortfolioSummaryResponse {
  total_balance: number;
  /** Free (unlocked) collateral inside the CollateralVault — tradeable margin. */
  free_margin: number;
  used_margin: number;
  unrealized_pnl: number;
  realized_pnl: number;
  /** Explicit vault-only balance (same as free_margin on current backends). */
  vault_free?: number;
  /** Test-USDC in the user's wallet, not yet deposited into the vault. */
  wallet_balance?: number;
}

// ============================================
// Backend API - Faucet
// ============================================

export interface FaucetClaimRequest {
  smart_account_address: string;
}

export interface FaucetClaimResponse {
  tx_hash: string;
  status: string;
}

export interface FaucetCooldownResponse {
  retry_after: number;
}

// ============================================
// Matching Engine (port 8001) - Orders
// ============================================

export type OrderType = 'limit' | 'market' | 'stop' | 'stop_loss' | 'take_profit';
export type Side = 'buy' | 'sell';
export type OrderStatus = 'open' | 'partially_filled' | 'filled' | 'cancelled' | 'rejected' | 'triggered';

export interface OrderRequest {
  basket_name: string;
  side?: Side | null;
  size?: number | null;
  leverage?: number | null;
  order_type?: OrderType;
  price?: number | null;
  max_slippage_bps?: number;
  trigger_price?: number | null;
  position_id?: string | null;
  oco_group_id?: string | null;
}

export interface OrderResponse {
  order_id: string;
  basket_name: string;
  trader: string;
  side: string;
  order_type: OrderType;
  price: number | null;
  trigger_price: number | null;
  size: number;
  filled_size: number;
  remaining: number;
  leverage: number;
  status: OrderStatus;
  rejection_reason: string | null;
  created_at: string;
  fills: FillResponse[];
  failed_fills: FillResponse[];
  margin_check: MarginCheckResponse | null;
  position_id: string | null;
  oco_group_id: string | null;
  average_fill_price: number | null;
}

export interface FillResponse {
  trade_id: string;
  basket_name: string;
  price: number;
  size: number;
  taker_order_id: string;
  maker_order_id: string;
  taker_trader: string;
  maker_trader: string;
  taker_side: string;
  maker_side: string;
  notional: number;
  confirmed: boolean;
  tx_hash: string | null;
  error: string | null;
  ts: string;
}

export interface MarginCheckResponse {
  ok: boolean;
  reason: string | null;
  details: Record<string, unknown>;
}

export interface OrderListItem {
  order_id: string;
  basket_name: string;
  side: string;
  order_type: OrderType;
  price: number | null;
  trigger_price: number | null;
  size: number;
  filled_size: number;
  remaining: number;
  leverage: number;
  status: OrderStatus;
  rejection_reason: string | null;
  created_at: string;
  updated_at: string;
  position_id: string | null;
  oco_group_id: string | null;
  average_fill_price: number | null;
}

export interface OrderListResponse {
  orders: OrderListItem[];
  cursor: string | null;
  has_more: boolean;
}

export interface CancelResponse {
  order_id: string;
  status: OrderStatus;
  message: string;
}

// ============================================
// Matching Engine - Order Book
// ============================================

export interface BookLevel {
  price: number;
  size: number;
}

export interface BookSnapshot {
  basket_name: string;
  bids: BookLevel[];
  asks: BookLevel[];
  best_bid: number | null;
  best_ask: number | null;
  mid_price: number | null;
  spread: number | null;
  ts: string;
}

// ============================================
// Matching Engine - Positions
// ============================================

export interface PositionResponse {
  position_id: string;
  basket_name: string;
  side: string;
  size: number;
  leverage: number;
  entry_price: number;
  mark_price: number;
  margin_usdc: number;
  liquidation_price: number | null;
  unrealized_pnl_abs: number;
  unrealized_pnl_pct: number;
  stop_loss_price: number | null;
  take_profit_price: number | null;
  stop_loss_order_id: string | null;
  take_profit_order_id: string | null;
  oco_group_id: string | null;
  fee_paid: number | null;
  opened_at: string;
}

export interface PositionsResponse {
  positions: PositionResponse[];
}

// ============================================
// Error Types
// ============================================

export interface ValidationError {
  loc: (string | number)[];
  msg: string;
  type: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
}

export interface HTTPValidationError {
  detail: ValidationError[];
}

// Rejection codes from API (422 detail strings)
export type RejectionCode =
  | 'oracle_price_stale'
  | 'insufficient_margin'
  | 'basket_not_tradeable'
  | 'price_not_on_tick'
  | 'size_below_min'
  | 'leverage_out_of_range'
  | 'leverage_above_cap'
  | 'oracle_price_zero'
  | 'unknown_basket'
  | 'max_slippage_bps_required'
  | 'trigger_price_required'
  | 'position_id_required'
  | 'price_required_for_limit_orders'
  | 'sl_tp_field_mismatch'
  | 'position_not_found'
  | 'no_liquidity'
  | 'insufficient_liquidity'
  | 'fok_failed'
  | 'self_trade'
  | 'oracle_unreadable'
  | 'leverage_cap_unreadable'
  | 'invalid_slippage_bps'
  | 'invalid_trigger_price'
  | 'settlement_failed'
  | 'oco_cancelled'
  | 'token_missing'
  | 'token_expired'
  | 'token_invalid';

// Auth error codes (401)
export type AuthErrorCode = 'token_missing' | 'token_expired' | 'token_invalid';

export const isAuthErrorCode = (code: string): code is AuthErrorCode => {
  return ['token_missing', 'token_expired', 'token_invalid'].includes(code);
};

export const isRejectionCode = (code: string): code is RejectionCode => {
  const codes: RejectionCode[] = [
    'oracle_price_stale', 'insufficient_margin', 'basket_not_tradeable',
    'price_not_on_tick', 'size_below_min', 'leverage_out_of_range',
    'leverage_above_cap', 'oracle_price_zero', 'unknown_basket',
    'max_slippage_bps_required', 'trigger_price_required', 'position_id_required',
    'price_required_for_limit_orders', 'sl_tp_field_mismatch', 'position_not_found',
    'no_liquidity', 'insufficient_liquidity', 'fok_failed', 'self_trade',
    'oracle_unreadable', 'leverage_cap_unreadable', 'invalid_slippage_bps',
    'invalid_trigger_price', 'settlement_failed', 'oco_cancelled'
  ];
  return codes.includes(code as RejectionCode);
};