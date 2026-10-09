import { useDynamicContext } from "@dynamic-labs/sdk-react-core";
import { Link } from "react-router-dom";
import type { Basket } from "@/lib/market-data";
import { track } from "@/lib/analytics";

const LOGO_SRC =
  "https://api.builder.io/api/v1/image/assets/TEMP/393e66ec13238cbe7c7af025ce6845c7bb6e3029?width=191";

export function SignInSheet({ basket, onClose }: { basket: Basket; onClose: () => void }) {
  const { setShowAuthFlow } = useDynamicContext();

  return (
    <div className="fixed inset-0 z-50 mx-auto flex max-w-md items-end justify-center">
      <div className="absolute inset-0 bg-neutral-950/88" onClick={onClose} />
      <div className="relative flex min-h-[62vh] w-full flex-col items-center justify-center gap-12 rounded-t-3xl border-x-[0.4px] border-t-[0.4px] border-neutral-800 bg-neutral-900 px-8 py-16">
        <img src={LOGO_SRC} alt="Xleuth logo" className="h-8 w-[100px] object-contain" />
        <div className="flex flex-col items-center gap-3">
          <p className="text-center text-base font-medium leading-[22px] tracking-[-0.18px] text-white">
            Sign in to trade {basket.symbol}
          </p>
          <p className="text-center text-[9px] leading-[10px] text-neutral-400">
            Create or log in with social accounts or connect wallet, export private key at
            conveniency.
          </p>
        </div>
        <div className="flex w-full flex-col items-center gap-3">
          <button
            onClick={() => {
              onClose();
              track("wallet_auth_opened");
              setShowAuthFlow(true);
            }}
            className="w-full rounded-lg bg-primary px-4 py-2 text-base text-white"
          >
            Sign in
          </button>
          <span className="text-center text-[9px] leading-[10px] text-neutral-400">
            Polygon Amoy testnet, no real fund involved yet.
          </span>
          <span className="text-center text-[9px] leading-[10px] text-neutral-500">
            By connecting you agree to the{" "}
            <Link to="/terms" onClick={onClose} className="underline underline-offset-2">
              Terms
            </Link>{" "}
            and acknowledge the{" "}
            <Link to="/privacy" onClick={onClose} className="underline underline-offset-2">
              Privacy Policy
            </Link>
            .
          </span>
        </div>
      </div>
    </div>
  );
}
