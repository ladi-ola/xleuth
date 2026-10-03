import type {
  OrderRequest,
  OrderResponse,
  OrderListResponse,
  OrderListItem,
  CancelResponse,
  BookSnapshot,
  PositionsResponse,
  PositionResponse,
  OrderType,
  Side,
  OrderStatus,
} from './schemas';

const MATCHING_ENGINE_URL = import.meta.env.VITE_MATCHING_ENGINE_URL || 'http://localhost:8001';

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

export const matchingApi = {
  // Orders
  async placeOrder(token: string, order: OrderRequest): Promise<OrderResponse> {
    const response = await fetch(`${MATCHING_ENGINE_URL}/orders`, {
      method: 'POST',
      headers: getAuthHeaders(token),
      body: JSON.stringify(order),
    });
    return handleResponse<OrderResponse>(response);
  },

  async getOrders(
    token: string,
    params?: {
      status?: 'open' | 'history' | 'all';
      basket_name?: string;
      limit?: number;
      cursor?: string;
    }
  ): Promise<OrderListResponse> {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status', params.status);
    if (params?.basket_name) searchParams.set('basket_name', params.basket_name);
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.cursor) searchParams.set('cursor', params.cursor);
    const query = searchParams.toString();
    const response = await fetch(
      `${MATCHING_ENGINE_URL}/orders${query ? `?${query}` : ''}`,
      { headers: getAuthHeaders(token) }
    );
    return handleResponse<OrderListResponse>(response);
  },

  async getOrder(token: string, orderId: string): Promise<OrderResponse> {
    const response = await fetch(`${MATCHING_ENGINE_URL}/orders/${encodeURIComponent(orderId)}`, {
      headers: getAuthHeaders(token),
    });
    return handleResponse<OrderResponse>(response);
  },

  async cancelOrder(token: string, orderId: string): Promise<CancelResponse> {
    const response = await fetch(`${MATCHING_ENGINE_URL}/orders/${encodeURIComponent(orderId)}`, {
      method: 'DELETE',
      headers: getAuthHeaders(token),
    });
    return handleResponse<CancelResponse>(response);
  },

  // Order Book
  async getOrderBook(basketName: string): Promise<BookSnapshot> {
    const response = await fetch(`${MATCHING_ENGINE_URL}/baskets/${encodeURIComponent(basketName)}/book`, {
      headers: { 'Content-Type': 'application/json' },
    });
    return handleResponse<BookSnapshot>(response);
  },

  // Positions
  async getPositions(token: string): Promise<PositionsResponse> {
    const response = await fetch(`${MATCHING_ENGINE_URL}/positions`, {
      headers: getAuthHeaders(token),
    });
    return handleResponse<PositionsResponse>(response);
  },
};

// WebSocket helpers
export const matchingWs = {
  // Matching engine doesn't have WebSocket endpoints per OpenAPI
  // Order book and price updates come from backend API WebSockets
};