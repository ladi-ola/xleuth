import {
  type LucideIcon,
  BookOpen,
  ChartColumnIncreasing,
  CircleQuestionMark,
  FileText,
  House,
  LifeBuoy,
  LogOut,
  Search,
  User,
} from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";
import { useDynamicContext } from "@dynamic-labs/sdk-react-core";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar";

const LOGO_SRC = "/brand/xleuth-wordmark.png";
const MARK_SRC = "/brand/xleuth-mark.png";

type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
  external?: boolean;
};

// Same destinations, order, icons and labels as the mobile bottom nav.
const primaryItems: NavItem[] = [
  { to: "/app", label: "Markets", icon: House, end: true },
  { to: "/explore", label: "Explore", icon: Search },
  { to: "/portfolio", label: "Portfolio", icon: ChartColumnIncreasing },
  { to: "/account", label: "Account", icon: User },
];

// Same secondary destinations as the mobile slide-out menu.
const secondaryItems: NavItem[] = [
  { to: "/how-it-works", label: "How it works", icon: CircleQuestionMark },
  {
    to: "/xleuth-whitepaper.pdf",
    label: "Whitepaper",
    icon: BookOpen,
    external: true,
  },
  {
    to: "/legal-risk-disclosure",
    label: "Legal & Risk disclosure",
    icon: FileText,
  },
  { to: "/support", label: "Support", icon: LifeBuoy },
  { to: "/privacy", label: "Privacy Policy", icon: FileText },
  { to: "/terms", label: "Terms", icon: FileText },
];

export function AppSidebar() {
  const { pathname } = useLocation();
  const { user, primaryWallet, handleLogOut, setShowAuthFlow } =
    useDynamicContext();

  const address = primaryWallet?.address;
  const shortAddress = address
    ? `${address.slice(0, 6)}...${address.slice(-4)}`
    : null;

  const isActive = (item: NavItem) =>
    !item.external &&
    (item.end
      ? pathname === item.to
      : pathname === item.to || pathname.startsWith(`${item.to}/`));

  return (
    <Sidebar variant="floating" collapsible="icon" aria-label="Primary">
      <SidebarHeader>
        <div className="flex h-10 items-center px-1 group-data-[collapsible=icon]:justify-center">
          <img
            src={LOGO_SRC}
            alt="xleuth"
            className="h-7 w-[88px] object-contain object-left group-data-[collapsible=icon]:hidden dark:invert"
          />
          <img
            src={MARK_SRC}
            alt=""
            aria-hidden
            className="hidden h-6 w-6 object-contain group-data-[collapsible=icon]:block dark:invert"
          />
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarMenu>
          {primaryItems.map((item) => (
            <SidebarMenuItem key={item.to}>
              <SidebarMenuButton
                asChild
                isActive={isActive(item)}
                tooltip={item.label}
              >
                <NavLink to={item.to} end={item.end}>
                  <item.icon strokeWidth={1.6} />
                  <span>{item.label}</span>
                </NavLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>

        <SidebarMenu className="mt-auto">
          {secondaryItems.map((item) => (
            <SidebarMenuItem key={item.to}>
              <SidebarMenuButton
                asChild
                isActive={isActive(item)}
                tooltip={item.label}
              >
                {item.external ? (
                  <a href={item.to} target="_blank" rel="noopener noreferrer">
                    <item.icon strokeWidth={1.4} />
                    <span>{item.label}</span>
                  </a>
                ) : (
                  <NavLink to={item.to}>
                    <item.icon strokeWidth={1.4} />
                    <span>{item.label}</span>
                  </NavLink>
                )}
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarContent>

      <SidebarFooter>
        {user && shortAddress ? (
          <div className="flex flex-col items-start gap-2 rounded-lg bg-muted p-3 group-data-[collapsible=icon]:hidden">
            <span className="text-[9px] leading-[10px] text-muted-foreground">
              Connected wallet
            </span>
            <span className="text-xs font-medium leading-4 tracking-[-0.12px] text-foreground">
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

        {user ? (
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton
                onClick={() => handleLogOut()}
                tooltip="Disconnect wallet"
                className="text-destructive hover:text-destructive"
              >
                <LogOut strokeWidth={1.4} />
                <span>Disconnect wallet</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        ) : (
          <>
            {pathname !== "/account" ? (
              <button
                onClick={() => setShowAuthFlow(true)}
                className="flex h-8 items-center justify-center rounded-lg bg-primary px-4 text-xs text-primary-foreground group-data-[collapsible=icon]:hidden"
              >
                Sign up
              </button>
            ) : null}
            <span className="px-2 text-[10px] leading-3 text-muted-foreground group-data-[collapsible=icon]:hidden">
              2026 • Xleuth - Polygon Amoy Testnet
            </span>
          </>
        )}
      </SidebarFooter>

      <SidebarRail />
    </Sidebar>
  );
}
