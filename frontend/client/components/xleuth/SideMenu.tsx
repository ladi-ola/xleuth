import { X, CircleQuestionMark, FileDown, FileText, LifeBuoy, LogOut } from "lucide-react";
import { useDynamicContext } from "@dynamic-labs/sdk-react-core";
import { useNavigate } from "react-router-dom";

export function SideMenu({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { user, handleLogOut, primaryWallet } = useDynamicContext();
  const navigate = useNavigate();

  const navigateTo = (path: string) => {
    navigate(path);
    onClose();
  };

  if (!open) return null;

  const address = primaryWallet?.address;
  const shortAddress = address
    ? `${address.slice(0, 6)}...${address.slice(-4)}`
    : null;

  return (
    <div className="fixed inset-0 z-50 mx-auto flex max-w-md justify-end">
      <div
        className="absolute inset-0 bg-neutral-950/88"
        onClick={onClose}
        aria-hidden
      />
      <div className="relative flex h-full w-[252px] flex-col rounded-l-xl bg-neutral-800">
        <div className="flex items-center justify-between border-b border-neutral-600/40 p-4">
            <span className="text-sm font-semibold leading-5 text-neutral-50">
              Menu
            </span>
            <button onClick={onClose} aria-label="Close menu">
              <X className="h-6 w-6 text-neutral-500" strokeWidth={2} />
            </button>
          </div>

        {user && shortAddress ? (
          <div className="flex flex-col items-start gap-2 border-b border-neutral-600/40 bg-neutral-800 p-4">
              <span className="text-[9px] leading-[10px] text-neutral-400">
                Connected wallet
              </span>
              <span className="text-xs font-medium leading-4 tracking-[-0.12px] text-neutral-200">
                {shortAddress}
              </span>
              <div className="flex items-center gap-1.5 rounded bg-warning/10 px-2 py-2">
                <span className="h-2 w-2 rounded-full bg-warning" />
                <span className="text-[10px] font-medium leading-3 text-warning">
                  Polygon Amoy (testnet)
                </span>
              </div>
          </div>
        ) : null}

        <div className="min-h-0 flex-1 overflow-y-auto p-4 pt-6">
          <div className="flex flex-col gap-8">
            <button
              onClick={() => navigateTo("/how-it-works")}
              className="flex items-center gap-2.5 text-left"
            >
              <CircleQuestionMark className="h-4 w-4 text-neutral-300" strokeWidth={1.4} />
              <span className="text-xs font-medium leading-4 text-neutral-300">
                How it works
              </span>
            </button>
            {/* Plain anchor (not a router link) so the SPA router does not
                intercept it; Vite serves public/ at the site root, so this
                resolves to https://<host>/xleuth-whitepaper.pdf. The download
                attribute keeps the stable filename. */}
            <a
              href="/xleuth-whitepaper.pdf"
              download="xleuth-whitepaper.pdf"
              onClick={onClose}
              className="flex items-center gap-2.5 text-left"
            >
              <FileDown className="h-4 w-4 text-neutral-300" strokeWidth={1.4} />
              <span className="text-xs font-medium leading-4 text-neutral-300">
                Whitepaper
              </span>
            </a>
            <button
              onClick={() => navigateTo("/legal-risk-disclosure")}
              className="flex items-center gap-2.5 text-left"
            >
              <FileText className="h-4 w-4 text-neutral-300" strokeWidth={1.4} />
              <span className="text-xs font-medium leading-4 text-neutral-300">
                Legal &amp; Risk disclosure
              </span>
            </button>
            <button
              onClick={() => navigateTo("/support")}
              className="flex items-center gap-2.5 text-left"
            >
              <LifeBuoy className="h-4 w-4 text-neutral-300" strokeWidth={1.4} />
              <span className="text-xs font-medium leading-4 text-neutral-300">
                Support
              </span>
            </button>
            <button
              onClick={() => navigateTo("/privacy")}
              className="flex items-center gap-2.5 text-left"
            >
              <FileText className="h-4 w-4 text-neutral-300" strokeWidth={1.4} />
              <span className="text-xs font-medium leading-4 text-neutral-300">
                Privacy Policy
              </span>
            </button>
            <button
              onClick={() => navigateTo("/terms")}
              className="flex items-center gap-2.5 text-left"
            >
              <FileText className="h-4 w-4 text-neutral-300" strokeWidth={1.4} />
              <span className="text-xs font-medium leading-4 text-neutral-300">
                Terms
              </span>
            </button>
          </div>
        </div>

        {user ? (
          <div className="shrink-0 border-t border-neutral-600/40 p-4">
            <button
              onClick={() => {
                handleLogOut();
                onClose();
              }}
              className="flex flex-1 items-center gap-2 rounded-lg px-2"
            >
              <LogOut className="h-4 w-4 text-destructive" strokeWidth={1.4} />
              <span className="text-sm font-medium leading-5 tracking-[-0.16px] text-destructive">
                Disconnect wallet
              </span>
            </button>
          </div>
        ) : (
          <div className="shrink-0 border-t border-neutral-600/40 p-4 text-center">
            <span className="text-[10px] leading-3 text-neutral-400">
              2026 • Xleuth - Polygon Amoy Testnet
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
