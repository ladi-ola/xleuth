import * as React from "react";
import { PropsWithChildren } from "react";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { AppSidebar } from "./AppSidebar";

/**
 * Desktop / tablet shell: a collapsible left sidebar replacing the mobile
 * bottom navigation, with the screen content in the inset scroll region.
 *
 * The sidebar starts expanded on wide desktops and as an icon rail on tablet
 * widths; it can be toggled via the rail or Ctrl/Cmd+B.
 */
export function DesktopLayout({ children }: PropsWithChildren) {
  const defaultOpen = React.useMemo(
    () => (typeof window !== "undefined" ? window.innerWidth >= 1024 : true),
    [],
  );

  return (
    <SidebarProvider defaultOpen={defaultOpen}>
      <AppSidebar />
      <SidebarInset className="my-2 mr-2 h-[calc(100svh-1rem)] min-h-0 overflow-hidden rounded-xl border-[0.4px] border-neutral-800 bg-neutral-950">
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </SidebarInset>
    </SidebarProvider>
  );
}
