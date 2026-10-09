import { useQuery, useQueries, useMutation, useQueryClient } from '@tanstack/react-query';
import { backendApi, matchingApi } from './index';
import { queryKeys, queryOptions } from './queryKeys';
import { authenticatedFetch, ApiError } from './token-exchange';
import { useDynamicContext } from '@dynamic-labs/sdk-react-core';
import { useToast } from '@/hooks/use-toast';

// ============================================
// Public queries (no auth required)
// ============================================

export function useBaskets() {
  return useQuery({
    queryKey: queryKeys.baskets.list(),
    queryFn: () => backendApi.getBaskets(),
    ...queryOptions.public,
  });
}

export function useBasketPrice(basketName: string | undefined) {
  return useQuery({
    queryKey: queryKeys.baskets.price(basketName || ''),
    queryFn: () => backendApi.getBasketPrice(basketName!),
    enabled: !!basketName,
    ...queryOptions.public,
  });
}

// The basket list endpoint does not return 24h change, so the list views
// enrich each basket with its own /price call (PLAN Section 5A item 1).
export function useBasketPrices(basketNames: string[]) {
  return useQueries({
    queries: basketNames.map((name) => ({
      queryKey: queryKeys.baskets.price(name),
      queryFn: () => backendApi.getBasketPrice(name),
      enabled: !!name,
      ...queryOptions.public,
    })),
  });
}

export function useBasketHistory(
  basketName: string | undefined,
  params?: { start?: string; end?: string; limit?: number }
) {
  return useQuery({
    queryKey: queryKeys.baskets.history(basketName || '', params),
    queryFn: () => backendApi.getBasketHistory(basketName!, params),
    enabled: !!basketName,
    ...queryOptions.public,
  });
}

export function useBasketConstituents(basketName: string | undefined) {
  return useQuery({
    queryKey: queryKeys.baskets.constituents(basketName || ''),
    queryFn: () => backendApi.getBasketConstituents(basketName!),
    enabled: !!basketName,
    ...queryOptions.public,
  });
}

export function useCandles(
  basketName: string | undefined,
  params?: { interval?: string; limit?: number; start?: string; end?: string }
) {
  return useQuery({
    queryKey: queryKeys.baskets.candles(basketName || '', params),
    queryFn: () => backendApi.getCandles(basketName!, params),
    enabled: !!basketName,
    ...queryOptions.public,
  });
}

export function useOrderBook(basketName: string | undefined) {
  return useQuery({
    queryKey: queryKeys.baskets.orderBook(basketName || ''),
    queryFn: () => matchingApi.getOrderBook(basketName!),
    enabled: !!basketName,
    ...queryOptions.public,
  });
}

// ============================================
// Authenticated queries
// ============================================

function useAuthEnabled(): boolean {
  const { user } = useDynamicContext();
  return !!user;
}

export function useAccount() {
  const enabled = useAuthEnabled();

  return useQuery({
    queryKey: queryKeys.account.me(),
    queryFn: () => authenticatedFetch(backendApi.getAccount),
    enabled,
    ...queryOptions.authenticated,
  });
}

export function usePortfolioSummary() {
  const enabled = useAuthEnabled();

  return useQuery({
    queryKey: queryKeys.account.summary(),
    queryFn: () => authenticatedFetch(backendApi.getSummary),
    enabled,
    ...queryOptions.authenticated,
  });
}

export function useTransactions(limit = 50) {
  const enabled = useAuthEnabled();

  return useQuery({
    queryKey: queryKeys.account.transactions(limit),
    queryFn: () => authenticatedFetch((token) => backendApi.getTransactions(token, limit)),
    enabled,
    ...queryOptions.authenticated,
  });
}

export function usePositions() {
  const enabled = useAuthEnabled();

  return useQuery({
    queryKey: queryKeys.positions.list(),
    queryFn: () => authenticatedFetch(matchingApi.getPositions),
    enabled,
    ...queryOptions.authenticated,
  });
}

export function useOpenOrders(basketName?: string) {
  const enabled = useAuthEnabled();

  return useQuery({
    queryKey: queryKeys.orders.open(basketName),
    queryFn: () => authenticatedFetch((token) => matchingApi.getOrders(token, { status: 'open', basket_name: basketName })),
    enabled,
    ...queryOptions.authenticated,
  });
}

export function useOrderHistory(basketName?: string, cursor?: string) {
  const enabled = useAuthEnabled();

  return useQuery({
    queryKey: queryKeys.orders.history(basketName, cursor),
    queryFn: () => authenticatedFetch((token) => matchingApi.getOrders(token, { status: 'history', basket_name: basketName, cursor })),
    enabled,
    ...queryOptions.authenticated,
  });
}

// ============================================
// Mutations
// ============================================

export function usePlaceOrder() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (order: Parameters<typeof matchingApi.placeOrder>[1]) =>
      authenticatedFetch((token) => matchingApi.placeOrder(token, order)),
    onMutate: async (newOrder) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: queryKeys.orders.all });
      await queryClient.cancelQueries({ queryKey: queryKeys.positions.all });
      await queryClient.cancelQueries({ queryKey: queryKeys.account.summary() });

      // Snapshot previous values
      const previousOrders = queryClient.getQueryData(queryKeys.orders.all);
      const previousPositions = queryClient.getQueryData(queryKeys.positions.list());
      const previousSummary = queryClient.getQueryData(queryKeys.account.summary());

      return { previousOrders, previousPositions, previousSummary };
    },
    onError: (error, _variables, context) => {
      // Rollback on error
      if (context?.previousOrders) {
        queryClient.setQueryData(queryKeys.orders.all, context.previousOrders);
      }
      if (context?.previousPositions) {
        queryClient.setQueryData(queryKeys.positions.list(), context.previousPositions);
      }
      if (context?.previousSummary) {
        queryClient.setQueryData(queryKeys.account.summary(), context.previousSummary);
      }

      const apiError = ApiError.fromUnknown(error);
      if (!apiError.status) {
        // Ambiguous failure (network error/timeout): never auto-retry POST
        // /orders (duplicate-order risk). Reconcile via GET /orders (the
        // onSettled invalidation below) and say so honestly.
        toast({
          title: 'Order status unknown',
          description: 'Network error. Check Portfolio open orders to reconcile.',
          variant: 'destructive',
        });
        return;
      }
      toast({
        title: 'Order Failed',
        description: apiError.message,
        variant: 'destructive',
      });
    },
    onSuccess: (_data, _variables, _context) => {
      // Invalidate and refetch
      queryClient.invalidateQueries({ queryKey: queryKeys.orders.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.positions.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.account.summary() });
    },
    onSettled: () => {
      // Always refetch after mutation
      queryClient.invalidateQueries({ queryKey: queryKeys.orders.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.positions.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.account.summary() });
    },
  });
}

export function useCancelOrder() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (orderId: string) => authenticatedFetch((token) => matchingApi.cancelOrder(token, orderId)),
    onMutate: async (orderId) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.orders.all });
      const previousOrders = queryClient.getQueryData(queryKeys.orders.all);
      return { previousOrders };
    },
    onError: (error, _variables, context) => {
      if (context?.previousOrders) {
        queryClient.setQueryData(queryKeys.orders.all, context.previousOrders);
      }
      const apiError = ApiError.fromUnknown(error);
      toast({
        title: 'Cancel Failed',
        description: apiError.message,
        variant: 'destructive',
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.orders.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.positions.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.account.summary() });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.orders.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.positions.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.account.summary() });
    },
  });
}

export function useFaucetClaim() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { primaryWallet } = useDynamicContext();

  return useMutation({
    mutationFn: async () => {
      // Phase 5: the recipient is always the caller's wallet_address from
      // /accounts/me. Prefer the cached account, fetch it when the cache is
      // cold, and fall back to the connected wallet (same EOA) only if the
      // account read fails. Never a free-text or user-supplied address.
      // Note: Backend currently expects smart_account_address.
      // With AA deferred, we pass the EOA address.
      const cachedAccount = queryClient.getQueryData<{ wallet_address?: string }>(
        queryKeys.account.me()
      );
      let address = cachedAccount?.wallet_address;
      if (!address) {
        try {
          const account = await authenticatedFetch(backendApi.getAccount);
          address = account.wallet_address;
        } catch {
          address = primaryWallet?.address;
        }
      }
      if (!address) {
        throw new Error('No wallet connected');
      }
      return authenticatedFetch((token) => backendApi.claimFaucet(token, address));
    },
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: queryKeys.account.all });
      const previousSummary = queryClient.getQueryData(queryKeys.account.summary());
      const previousAccount = queryClient.getQueryData(queryKeys.account.me());
      return { previousSummary, previousAccount };
    },
    onError: (error, _variables, context) => {
      if (context?.previousSummary) {
        queryClient.setQueryData(queryKeys.account.summary(), context.previousSummary);
      }
      if (context?.previousAccount) {
        queryClient.setQueryData(queryKeys.account.me(), context.previousAccount);
      }
      const apiError = ApiError.fromUnknown(error);
      if (!apiError.status) {
        // Ambiguous failure (network error/timeout): never auto-retry the
        // claim (double-funding risk). The onSettled invalidation below
        // re-reads the balance; tell the user to reconcile from it.
        toast({
          title: 'Claim status unknown',
          description: 'Network error. Balance re-read — check for updated funds.',
          variant: 'destructive',
        });
        return;
      }
      toast({
        title: apiError.isCooldown() ? 'Faucet Cooldown' : 'Claim Failed',
        description: apiError.message,
        variant: 'destructive',
      });
    },
    onSuccess: (data) => {
      toast({
        title: 'Claim Successful',
        description: `Transaction: ${data.tx_hash}`,
        variant: 'destructive', // Using destructive as success variant may not exist
      });
      // Invalidate to refetch balance
      queryClient.invalidateQueries({ queryKey: queryKeys.account.all });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.account.all });
    },
  });
}

// ============================================
// Prefetching helpers
// ============================================

export function usePrefetchBasket(basketName: string) {
  const queryClient = useQueryClient();

  return () => {
    queryClient.prefetchQuery({
      queryKey: queryKeys.baskets.price(basketName),
      queryFn: () => backendApi.getBasketPrice(basketName),
      ...queryOptions.public,
    });
    queryClient.prefetchQuery({
      queryKey: queryKeys.baskets.constituents(basketName),
      queryFn: () => backendApi.getBasketConstituents(basketName),
      ...queryOptions.public,
    });
  };
}