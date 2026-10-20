import { useDynamicContext } from "@dynamic-labs/sdk-react-core";
import { Link } from "react-router-dom";
import type { Basket } from "@/lib/market-data";
import { track } from "@/lib/analytics";

const LOGO_SRC = "/brand/xleuth-wordmark.png";

export function SignInSheet({
  basket,
  onClose,
}: {
  basket: Basket;
  onClose: () => void;
}) {
  const { setShowAuthFlow } = useDynamicContext();

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center md:items-center md:px-4">
      <div className="absolute inset-0 bg-black/45" onClick={onClose} />
      <div className="relative flex min-h-[62vh] w-full max-w-md flex-col items-center justify-center gap-12 rounded-t-3xl border-x-[0.4px] border-t-[0.4px] border-border bg-card px-8 py-16 md:min-h-0 md:rounded-3xl md:border-[0.4px]">
        <img
          src={LOGO_SRC}
          alt="Xleuth logo"
          className="h-8 w-[100px] object-contain dark:invert"
        />
        <div className="flex flex-col items-center gap-3">
          <p className="text-center text-base font-medium leading-[22px] tracking-[-0.18px] text-foreground">
            Sign in to trade {basket.symbol}
          </p>
          <p className="text-center text-[9px] leading-[10px] text-muted-foreground">
            Create or log in with social accounts or connect wallet, export
            private key at conveniency.
          </p>
        </div>
        <div className="flex w-full flex-col items-center gap-3">
          <button
            onClick={() => {
              onClose();
              track("wallet_auth_opened");
              setShowAuthFlow(true);
            }}
            className="w-full rounded-lg bg-primary px-4 py-2 text-base text-primary-foreground"
          >
            Sign in
          </button>
          <span className="text-center text-[9px] leading-[10px] text-muted-foreground">
            Polygon Amoy testnet, no real fund involved yet.
          </span>
          <span className="text-center text-[9px] leading-[10px] text-muted-foreground">
            By connecting you agree to the{" "}
            <Link
              to="/terms"
              onClick={onClose}
              className="underline underline-offset-2"
            >
              Terms
            </Link>{" "}
            and acknowledge the{" "}
            <Link
              to="/privacy"
              onClick={onClose}
              className="underline underline-offset-2"
            >
              Privacy Policy
            </Link>
            .
          </span>
        </div>
      </div>
    </div>
  );
}
