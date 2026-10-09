// URL helpers: prevent mixed content on HTTPS deployments (task 4).
//
// Production env vars must already be https/wss, but if the page itself is
// served over HTTPS and a URL is still http/ws (e.g. a localhost default
// leaking into prod), upgrade it instead of letting the browser block it.

export function secureUrl(url: string): string {
  try {
    if (typeof window !== 'undefined' && window.location?.protocol === 'https:') {
      if (url.startsWith('http://')) return 'https://' + url.slice('http://'.length);
      if (url.startsWith('ws://')) return 'wss://' + url.slice('ws://'.length);
    }
  } catch {
    // Non-browser context (tests/SSR): return unchanged.
  }
  return url;
}
