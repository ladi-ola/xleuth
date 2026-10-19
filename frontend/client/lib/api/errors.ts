import type { HTTPValidationError, RejectionCode, AuthErrorCode } from './schemas';
import { isAuthErrorCode, isRejectionCode } from './schemas';
import { MIN_ORDER_CONTRACTS } from './limits';

// Rejection code to user-friendly message mapping
export const REJECTION_MESSAGES: Record<Exclude<RejectionCode, AuthErrorCode>, string> = {
  oracle_price_stale: 'Price feed is stale. Please try again.',
  insufficient_margin: 'Insufficient margin for this order.',
  basket_not_tradeable: 'This market is not currently tradeable.',
  price_not_on_tick: 'Price must be on a valid tick (0.01 increments).',
  size_below_min: `Order size is below the minimum of ${MIN_ORDER_CONTRACTS} contracts. Increase the order size.`,
  leverage_out_of_range: 'Leverage must be between 1x and 5x.',
  leverage_above_cap: 'Leverage exceeds the maximum allowed for this market.',
  oracle_price_zero: 'Oracle price is unavailable.',
  unknown_basket: 'Unknown market.',
  max_slippage_bps_required: 'Max slippage (bps) is required for this order type.',
  trigger_price_required: 'Trigger price is required for this order type.',
  position_id_required: 'Position ID is required for stop-loss/take-profit orders.',
  price_required_for_limit_orders: 'Price is required for limit orders.',
  sl_tp_field_mismatch: 'Stop-loss/take-profit fields must match the existing position.',
  position_not_found: 'Position not found.',
  no_liquidity: 'No liquidity available.',
  insufficient_liquidity: 'Insufficient liquidity for this order size.',
  fok_failed: 'Fill-or-kill order could not be filled.',
  self_trade: 'Order would result in self-trade.',
  oracle_unreadable: 'Oracle price could not be read.',
  leverage_cap_unreadable: 'Leverage cap could not be determined.',
  invalid_slippage_bps: 'Invalid slippage value.',
  invalid_trigger_price: 'Invalid trigger price.',
  settlement_failed: 'Order settlement failed.',
  oco_cancelled: 'OCO order was cancelled.',
};

export const AUTH_ERROR_MESSAGES: Record<AuthErrorCode, string> = {
  token_missing: 'Authentication required. Please sign in.',
  token_expired: 'Session expired. Please sign in again.',
  token_invalid: 'Invalid session. Please sign in again.',
};

export function getRejectionMessage(code: string): string {
  if (isRejectionCode(code)) {
    return REJECTION_MESSAGES[code] || `Order rejected: ${code}`;
  }
  if (isAuthErrorCode(code)) {
    return AUTH_ERROR_MESSAGES[code] || `Authentication error: ${code}`;
  }
  return `Error: ${code}`;
}

export function parseApiError(error: unknown): {
  message: string;
  code?: string;
  status?: number;
  retryAfter?: number;
  validationErrors?: Array<{ field: string; message: string }>;
} {
  const apiError = error as Error & {
    status?: number;
    data?: unknown;
    retryAfter?: number;
  };

  const status = apiError.status;
  const data = apiError.data as HTTPValidationError | { detail?: string } | undefined;

  // 401 auth errors
  if (status === 401) {
    const detail = typeof data?.detail === 'string' ? data.detail : '';
    if (isAuthErrorCode(detail)) {
      return { message: AUTH_ERROR_MESSAGES[detail], code: detail, status: 401 };
    }
    return { message: 'Authentication required. Please sign in.', code: 'token_invalid', status: 401 };
  }

  // 403 forbidden
  if (status === 403) {
    return { message: 'You are not authorized to perform this action.', status: 403 };
  }

  // 422 validation errors (FastAPI style)
  if (status === 422 && data?.detail && Array.isArray(data.detail)) {
    const validationErrors = data.detail.map((err) => ({
      field: err.loc.slice(-1)[0] as string,
      message: err.msg,
    }));
    const firstError = data.detail[0];
    const code = typeof firstError?.msg === 'string' ? firstError.msg : '';
    if (isRejectionCode(code)) {
      return { message: REJECTION_MESSAGES[code], code, status: 422, validationErrors };
    }
    if (isAuthErrorCode(code)) {
      return { message: AUTH_ERROR_MESSAGES[code], code, status: 422, validationErrors };
    }
    return {
      message: validationErrors.map((e) => `${e.field}: ${e.message}`).join(', '),
      status: 422,
      validationErrors,
    };
  }

  // 429 faucet cooldown
  if (status === 429) {
    const retryAfter = apiError.retryAfter || (typeof data === 'object' && data && 'retry_after' in data
      ? (data as { retry_after: number }).retry_after
      : 0);
    return {
      message: `Faucet on cooldown. Try again in ${retryAfter} seconds.`,
      code: 'cooldown',
      status: 429,
      retryAfter,
    };
  }

  // Other errors with detail string
  if (data && typeof data === 'object' && 'detail' in data && typeof data.detail === 'string') {
    const detail = data.detail;
    if (isRejectionCode(detail)) {
      return { message: REJECTION_MESSAGES[detail], code: detail, status };
    }
    if (isAuthErrorCode(detail)) {
      return { message: AUTH_ERROR_MESSAGES[detail], code: detail, status };
    }
    return { message: detail, status };
  }

  // Fallback
  return {
    message: apiError.message || 'An unexpected error occurred',
    status,
  };
}

export class ApiError extends Error {
  public readonly status: number;
  public readonly code?: string;
  public readonly retryAfter?: number;
  public readonly validationErrors?: Array<{ field: string; message: string }>;

  constructor(
    message: string,
    options: {
      status: number;
      code?: string;
      retryAfter?: number;
      validationErrors?: Array<{ field: string; message: string }>;
    }
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = options.status;
    this.code = options.code;
    this.retryAfter = options.retryAfter;
    this.validationErrors = options.validationErrors;
  }

  static fromUnknown(error: unknown): ApiError {
    const parsed = parseApiError(error);
    return new ApiError(parsed.message, {
      status: parsed.status || 500,
      code: parsed.code,
      retryAfter: parsed.retryAfter,
      validationErrors: parsed.validationErrors,
    });
  }

  isAuthError(): boolean {
    return this.status === 401 || this.status === 403 || this.code === 'token_expired' || this.code === 'token_invalid';
  }

  isRetryable(): boolean {
    // Only retry on 401 (token expired/invalid) - re-exchange token and retry once
    return this.status === 401 && (this.code === 'token_expired' || this.code === 'token_invalid');
  }

  isCooldown(): boolean {
    return this.status === 429 || this.code === 'cooldown';
  }
}