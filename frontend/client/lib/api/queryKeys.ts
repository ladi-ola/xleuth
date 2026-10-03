// TanStack Query key factories for consistent caching

export const queryKeys = {
  // Public (no auth)
  baskets: {
    all: ['baskets'] as const,
    list: () => [...queryKeys.baskets.all, 'list'] as const,
    price: (basketName: string) => [...queryKeys.baskets.all, 'price', basketName] as const,
    history: (basketName: string, params?: { start?: string; end?: string; limit?: number }) =>
      [...queryKeys.baskets.all, 'history', basketName, params] as const,
    constituents: (basketName: string) =>
      [...queryKeys.baskets.all, 'constituents', basketName] as const,
    candles: (basketName: string, params?: { interval?: string; limit?: number; start?: string; end?: string }) =>
      [...queryKeys.baskets.all, 'candles', basketName, params] as const,
    orderBook: (basketName: string) => [...queryKeys.baskets.all, 'orderBook', basketName] as const,
  },

  // Authenticated
  auth: {
    all: ['auth'] as const,
    me: () => [...queryKeys.auth.all, 'me'] as const,
  },

  account: {
    all: ['account'] as const,
    me: () => [...queryKeys.account.all, 'me'] as const,
    transactions: (limit?: number) => [...queryKeys.account.all, 'transactions', limit] as const,
    summary: () => [...queryKeys.account.all, 'summary'] as const,
  },

  positions: {
    all: ['positions'] as const,
    list: () => [...queryKeys.positions.all, 'list'] as const,
  },

  orders: {
    all: ['orders'] as const,
    open: (basketName?: string) => [...queryKeys.orders.all, 'open', basketName] as const,
    history: (basketName?: string, cursor?: string) =>
      [...queryKeys.orders.all, 'history', basketName, cursor] as const,
    allStatus: (status: 'open' | 'history' | 'all', basketName?: string, cursor?: string) =>
      [...queryKeys.orders.all, status, basketName, cursor] as const,
    detail: (orderId: string) => [...queryKeys.orders.all, 'detail', orderId] as const,
  },

  faucet: {
    all: ['faucet'] as const,
    claim: () => [...queryKeys.faucet.all, 'claim'] as const,
  },
};

// Query options defaults
export const queryOptions = {
  // Public data - cache for 30 seconds, stale after 10 seconds
  public: {
    staleTime: 10_000,
    gcTime: 30_000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: true,
  },

  // Authenticated data - cache for 15 seconds, stale after 5 seconds
  // Polling interval aligned with backend's ~5s trigger cycle
  authenticated: {
    staleTime: 5_000,
    gcTime: 15_000,
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
    refetchInterval: 10_000, // 10 seconds polling while mounted
  },

  // Real-time data (price, orderbook) - no caching, WS handles updates
  realtime: {
    staleTime: 0,
    gcTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  },
};

// Helper to pause queries when tab is hidden
export function createVisibilityAwareQueryOptions<T>(baseOptions: {
  enabled?: boolean;
  refetchInterval?: number | false;
}) {
  // This would be used with a custom hook that checks document.visibilityState
  // For now, return base options - we'll implement the visibility check in the hooks
  return baseOptions;
}