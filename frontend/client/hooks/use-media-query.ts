import * as React from "react";

/**
 * Subscribes to a CSS media query and returns whether it currently matches.
 *
 * The initial value is computed synchronously during the first render (via a
 * lazy useState initializer) so there is no flash of the wrong layout. This is
 * safe because the app is rendered purely on the client (see App.tsx), so
 * `window` is always available here.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = React.useState<boolean>(() =>
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia(query).matches
      : false,
  );

  React.useEffect(() => {
    if (
      typeof window === "undefined" ||
      typeof window.matchMedia !== "function"
    ) {
      return;
    }

    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);

    mql.addEventListener("change", onChange);
    // Re-sync in case the viewport changed between render and effect.
    setMatches(mql.matches);

    return () => mql.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

/**
 * Tablet and up. Matches the project's existing tablet breakpoint (768px),
 * which is also the cutoff used by `useIsMobile`.
 */
export function useIsTablet(): boolean {
  return useMediaQuery("(min-width: 768px)");
}

/**
 * Tablet (landscape) and up. Used for denser, multi-column desktop layouts.
 */
export function useIsDesktop(): boolean {
  return useMediaQuery("(min-width: 1024px)");
}
