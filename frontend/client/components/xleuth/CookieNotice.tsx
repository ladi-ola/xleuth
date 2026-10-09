import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { analyticsEnabled } from "@/lib/analytics";

const DISMISS_KEY = "xleuth-cookie-notice-dismissed";

// Task 5: short notice (not a consent wall). Audit result: the app sets no
// non-essential storage — auth token lives in memory, the only cookie is a
// functional sidebar preference, and analytics is cookieless AND off unless
// the operator configures it. So this notice only informs + links policy.
export function CookieNotice() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    try {
      if (!localStorage.getItem(DISMISS_KEY)) setVisible(true);
    } catch {
      setVisible(true);
    }
  }, []);

  if (!visible) return null;

  const dismiss = () => {
    try {
      localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      // Private mode: just hide for this session.
    }
    setVisible(false);
  };

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed inset-x-0 bottom-16 z-40 mx-auto flex max-w-md items-center gap-3 px-4"
    >
      <div className="flex w-full items-center gap-3 rounded-xl border-[0.4px] border-neutral-600 bg-neutral-900/95 p-3 shadow-lg">
        <p className="flex-1 text-[11px] leading-4 text-neutral-300">
          Xleuth uses strictly necessary storage only (sign-in session, wallet
          connection{analyticsEnabled() ? ", plus cookieless usage counts" : ""}). See the{" "}
          <Link to="/privacy" className="underline underline-offset-2">
            Privacy Policy
          </Link>
          .
        </p>
        <button
          onClick={dismiss}
          className="shrink-0 rounded-lg bg-primary px-3 py-1.5 text-xs text-white"
        >
          Got it
        </button>
      </div>
    </div>
  );
}
