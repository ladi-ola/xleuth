import { Menu } from "lucide-react";
import { useState } from "react";
import { useDynamicContext } from "@dynamic-labs/sdk-react-core";
import { useLocation } from "react-router-dom";
import { SideMenu } from "./SideMenu";

const LOGO_SRC = "/brand/xleuth-wordmark.png";

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
          className="h-8 w-[100px] object-contain object-left dark:invert"
        />
        <div className="flex items-center gap-3">
          {user ? (
            <button className="flex h-8 items-center justify-center rounded-lg border-[0.8px] border-border px-4 text-xs text-foreground/80">
              Amoy
            </button>
          ) : pathname !== "/account" ? (
            <button
              onClick={() => setShowAuthFlow(true)}
              className="flex h-8 items-center justify-center rounded-lg bg-primary px-4 text-xs text-primary-foreground"
            >
              Sign up
            </button>
          ) : null}
          <button onClick={() => setMenuOpen(true)} aria-label="Open menu">
            <Menu className="h-6 w-6 text-foreground" strokeWidth={2} />
          </button>
        </div>
      </div>
      <SideMenu open={menuOpen} onClose={() => setMenuOpen(false)} />
    </>
  );
}
