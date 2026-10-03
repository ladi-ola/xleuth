import type {
  BasketInfo,
  BasketListResponse,
  BasketPriceResponseWithChange,
  BasketHistoryResponse,
  BasketDetail,
  CandlesResponse,
  Candle,
  TokenResponse,
  UserInfo,
  TransactionHistoryResponse,
  PortfolioSummaryResponse,
  FaucetClaimRequest,
  FaucetClaimResponse,
  FaucetCooldownResponse,
  DynamicVerifyRequest,
  HTTPValidationError,
} from './schemas';

const BACKEND_API_URL = import.meta.env.VITE_BACKEND_API_URL || 'http://localhost:8000';

function getAuthHeaders(token?: string): HeadersInit {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorData: unknown;
    try {
      errorData = await response.json();
    } catch {
      errorData = { message: response.statusText };
    }
    const error = new Error(`API Error: ${response.status}`) as Error & {
      status: number;
      data?: unknown;
    };
    error.status = response.status;
    error.data = errorData;
    throw error;
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json();
}

export const backendApi = {
  // Auth
  async verifyToken(dynamicToken: string): Promise<TokenResponse> {
    const response = await fetch(`${BACKEND_API_URL}/auth/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: dynamicToken } satisfies DynamicVerifyRequest),
    });
    return handleResponse<TokenResponse>(response);
  },

  // Baskets
  async getBaskets(): Promise<BasketListResponse> {
    const response = await fetch(`${BACKEND_API_URL}/baskets`, {
      headers: { 'Content-Type': 'application/json' },
    });
    return handleResponse<BasketListResponse>(response);
  },

  async getBasketPrice(basketName: string): Promise<BasketPriceResponseWithChange> {
    const response = await fetch(`${BACKEND_API_URL}/baskets/${encodeURIComponent(basketName)}/price`, {
      headers: { 'Content-Type': 'application/json' },
    });
    return handleResponse<BasketPriceResponseWithChange>(response);
  },

  async getBasketHistory(
    basketName: string,
    params?: { start?: string; end?: string; limit?: number }
  ): Promise<BasketHistoryResponse> {
    const searchParams = new URLSearchParams();
    if (params?.start) searchParams.set('start', params.start);
    if (params?.end) searchParams.set('end', params.end);
    if (params?.limit) searchParams.set('limit', String(params.limit));
    const query = searchParams.toString();
    const response = await fetch(
      `${BACKEND_API_URL}/baskets/${encodeURIComponent(basketName)}/history${query ? `?${query}` : ''}`,
      { headers: { 'Content-Type': 'application/json' } }
    );
    return handleResponse<BasketHistoryResponse>(response);
  },

  async getBasketConstituents(basketName: string): Promise<BasketDetail> {
    const response = await fetch(`${BACKEND_API_URL}/baskets/${encodeURIComponent(basketName)}/constituents`, {
      headers: { 'Content-Type': 'application/json' },
    });
    return handleResponse<BasketDetail>(response);
  },

  async getCandles(
    basketName: string,
    params?: { interval?: string; limit?: number; start?: string; end?: string }
  ): Promise<CandlesResponse> {
    const searchParams = new URLSearchParams();
    if (params?.interval) searchParams.set('interval', params.interval);
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.start) searchParams.set('start', params.start);
    if (params?.end) searchParams.set('end', params.end);
    const query = searchParams.toString();
    const response = await fetch(
      `${BACKEND_API_URL}/baskets/${encodeURIComponent(basketName)}/candles${query ? `?${query}` : ''}`,
      { headers: { 'Content-Type': 'application/json' } }
    );
    return handleResponse<CandlesResponse>(response);
  },

  // Accounts (authenticated)
  async getAccount(token: string): Promise<UserInfo> {
    const response = await fetch(`${BACKEND_API_URL}/accounts/me`, {
      headers: getAuthHeaders(token),
    });
    return handleResponse<UserInfo>(response);
  },

  async updateAlias(token: string, alias: string): Promise<UserInfo> {
    const response = await fetch(`${BACKEND_API_URL}/accounts/alias?alias=${encodeURIComponent(alias)}`, {
      method: 'PUT',
      headers: getAuthHeaders(token),
    });
    return handleResponse<UserInfo>(response);
  },

  async getTransactions(token: string, limit = 50): Promise<TransactionHistoryResponse> {
    const response = await fetch(`${BACKEND_API_URL}/accounts/transactions?limit=${limit}`, {
      headers: getAuthHeaders(token),
    });
    return handleResponse<TransactionHistoryResponse>(response);
  },

  async getSummary(token: string): Promise<PortfolioSummaryResponse> {
    const response = await fetch(`${BACKEND_API_URL}/accounts/summary`, {
      headers: getAuthHeaders(token),
    });
    return handleResponse<PortfolioSummaryResponse>(response);
  },

  // Faucet
  async claimFaucet(token: string, smartAccountAddress: string): Promise<FaucetClaimResponse> {
    const response = await fetch(`${BACKEND_API_URL}/faucet/claim`, {
      method: 'POST',
      headers: getAuthHeaders(token),
      body: JSON.stringify({ smart_account_address: smartAccountAddress } satisfies FaucetClaimRequest),
    });
    if (response.status === 429) {
      const data = await handleResponse<FaucetCooldownResponse>(response);
      const error = new Error('Faucet cooldown active') as Error & { status: number; retryAfter: number };
      error.status = 429;
      error.retryAfter = data.retry_after;
      throw error;
    }
    return handleResponse<FaucetClaimResponse>(response);
  },
};

// WebSocket helpers
export const backendWs = {
  getPriceWsUrl(basketName: string): string {
    const base = import.meta.env.VITE_BACKEND_WS_URL || 'ws://localhost:8000';
    return `${base}/ws/price/${encodeURIComponent(basketName)}`;
  },

  getOrderBookWsUrl(basketName: string): string {
    const base = import.meta.env.VITE_BACKEND_WS_URL || 'ws://localhost:8000';
    return `${base}/ws/orderbook/${encodeURIComponent(basketName)}`;
  },
};