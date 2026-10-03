import { backendApi } from './backend';
import { ApiError } from './errors';
import { getAuthToken } from '@dynamic-labs/sdk-react-core';

interface TokenState {
  accessToken: string | null;
  expiresAt: number; // timestamp in ms
}

// In-memory token storage (not persisted to localStorage)
let tokenState: TokenState = {
  accessToken: null,
  expiresAt: 0,
};

let refreshPromise: Promise<string> | null = null;

function isTokenValid(): boolean {
  return tokenState.accessToken !== null && Date.now() < tokenState.expiresAt - 60_000; // 1 min buffer
}

/**
 * Exchange a Dynamic JWT for an internal backend token.
 * Uses getAuthToken from Dynamic SDK to retrieve the current JWT.
 */
export async function exchangeDynamicToken(): Promise<string> {
  // Return cached token if valid
  if (isTokenValid()) {
    return tokenState.accessToken!;
  }

  // If a refresh is already in progress, wait for it
  if (refreshPromise) {
    return refreshPromise;
  }

  // Get Dynamic JWT from SDK
  const dynamicToken = getAuthToken();

  if (!dynamicToken) {
    throw new ApiError('Not authenticated', { status: 401, code: 'token_missing' });
  }

  // Exchange Dynamic token for internal token
  refreshPromise = (async () => {
    try {
      const response = await backendApi.verifyToken(dynamicToken);
      tokenState = {
        accessToken: response.access_token,
        expiresAt: Date.now() + response.expires_in_minutes * 60 * 1000,
      };
      return tokenState.accessToken!;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

export function clearInternalToken(): void {
  tokenState = { accessToken: null, expiresAt: 0 };
  refreshPromise = null;
}

export function getCachedToken(): string | null {
  return isTokenValid() ? tokenState.accessToken : null;
}

// Utility for making authenticated requests with automatic 401 retry
export async function authenticatedFetch<T>(
  fetchFn: (token: string) => Promise<T>,
  maxRetries = 1
): Promise<T> {
  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const token = await exchangeDynamicToken();
      return await fetchFn(token);
    } catch (error) {
      lastError = error as Error;

      // Check if it's a 401 that we can retry
      const apiError = error as { status?: number; code?: string };
      if (
        apiError.status === 401 &&
        (apiError.code === 'token_expired' || apiError.code === 'token_invalid') &&
        attempt < maxRetries
      ) {
        // Clear token to force re-exchange
        clearInternalToken();
        continue;
      }

      throw error;
    }
  }

  throw lastError;
}

// Re-export ApiError for consumers
export { ApiError } from './errors';