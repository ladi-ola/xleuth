import { Menu } from "lucide-react";
import { useState } from "react";
import { useDynamicContext } from "@dynamic-labs/sdk-react-core";
import { useLocation } from "react-router-dom";
import { SideMenu } from "./SideMenu";

const LOGO_SRC =
  "https://api.builder.io/api/v1/image/assets/TEMP/393e66ec13238cbe7c7af025ce6845c7bb6e3029?width=191";

export function TopBar() {
  const [menuOpen, setMenuOpen] = useState(false);
  const { pathname } = useLocation();
  const { user, setShowAuthFlow } = useDynamicContext();

  return (
    <>
      <div className="flex h-14 w-full items-center justify-between px-4 pt-6">
        <img
          src={LOGO_SRC}
          alt="xleuth brand logo tightly cropped 1"
          className="h-8 w-[100px] object-contain object-left"
        />
        <div className="flex items-center gap-3">
          {user ? (
            <button className="flex h-8 items-center justify-center rounded-lg border-[0.8px] border-neutral-600 px-4 text-xs text-neutral-300">
              Amoy
            </button>
          ) : pathname !== "/account" ? (
            <button
              onClick={() => setShowAuthFlow(true)}
              className="flex h-8 items-center justify-center rounded-lg bg-primary px-4 text-xs text-white"
            >
              Sign up
            </button>
          ) : null}
          <button onClick={() => setMenuOpen(true)} aria-label="Open menu">
            <Menu className="h-6 w-6 text-neutral-50" strokeWidth={2} />
          </button>
        </div>
      </div>
      <SideMenu open={menuOpen} onClose={() => setMenuOpen(false)} />
    </>
  );
}
