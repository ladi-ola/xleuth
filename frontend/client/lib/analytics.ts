// Privacy-friendly analytics (tasks 5 + 17).
//
// - Cookieless: plain fetch POST, no cookies, no fingerprinting, no SDK.
// - Disabled unless BOTH env vars are set (default: off, nothing loads):
//     VITE_ANALYTICS_URL  — collection endpoint (self-hosted Umami/Plausible proxy)
//     VITE_ANALYTICS_SITE — website id / domain configured on that endpoint
// - Respects Do Not Track and Global Privacy Control automatically.
// - track() takes an event NAME ONLY — there is no props parameter, so wallet
//   addresses, signatures, balances and tokens can never be sent as properties.
//   Events are client-side submission signals, not chain confirmations.

const ANALYTICS_URL: string = import.meta.env.VITE_ANALYTICS_URL || '';
const ANALYTICS_SITE: string = import.meta.env.VITE_ANALYTICS_SITE || '';
const OPTOUT_KEY = 'xleuth-analytics-optout';

export function analyticsEnabled(): boolean {
  if (!ANALYTICS_URL || !ANALYTICS_SITE) return false;
  try {
    if (typeof localStorage !== 'undefined' && localStorage.getItem(OPTOUT_KEY) === '1') return false;
    const nav = navigator as Navigator & { globalPrivacyControl?: boolean };
    if (nav.doNotTrack === '1') return false;
    if (nav.globalPrivacyControl === true) return false;
  } catch {
    return false;
  }
  return true;
}

export function optOutAnalytics(): void {
  try {
    localStorage.setItem(OPTOUT_KEY, '1');
  } catch {
    // Storage unavailable: analytics stays governed by DNT/env.
  }
}

export function track(name: string): void {
  if (!analyticsEnabled()) return;
  try {
    const body = {
      website: ANALYTICS_SITE,
      name,
      url: window.location.href,
      referrer: document.referrer || undefined,
    };
    // keepalive: survives route changes; never awaited, never blocks render.
    fetch(ANALYTICS_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      keepalive: true,
    }).catch(() => {});
  } catch {
    // Analytics must never break the app.
  }
}

export function pageview(path: string): void {
  track(`page_view:${path}`);
}
