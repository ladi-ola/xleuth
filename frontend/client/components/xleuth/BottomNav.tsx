import { House, Search, ChartColumnIncreasing, User } from "lucide-react";
import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";

const items = [
  { to: "/", label: "Markets", icon: House, end: true },
  { to: "/explore", label: "Explore", icon: Search },
  { to: "/portfolio", label: "Portfolio", icon: ChartColumnIncreasing },
  { to: "/account", label: "Account", icon: User },
];

export function BottomNav() {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 mx-auto flex h-16 w-full max-w-md items-center justify-between bg-background/80 px-6 py-1 backdrop-blur-md">
      {items.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className="flex w-[57px] flex-col items-center justify-end gap-1 py-2.5"
        >
          {({ isActive }) => (
            <>
              <Icon
                className={cn(
                  "h-6 w-6",
                  isActive ? "text-foreground" : "text-muted-foreground",
                )}
                strokeWidth={1.6}
              />
              <span
                className={cn(
                  "text-center text-[9px] font-medium leading-[10px]",
                  isActive ? "text-foreground" : "text-muted-foreground",
                )}
              >
                {label}
              </span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}
