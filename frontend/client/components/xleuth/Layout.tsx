import { PropsWithChildren } from "react";
import { TopBar } from "./TopBar";
import { BottomNav } from "./BottomNav";
import { DesktopLayout } from "./desktop/DesktopLayout";
import { useIsTablet } from "@/hooks/use-media-query";
import { cn } from "@/lib/utils";

type LayoutWidth = "md" | "lg" | "xl" | "full";

const WIDTH_CLASSES: Record<LayoutWidth, string> = {
  md: "max-w-3xl",
  lg: "max-w-4xl",
  xl: "max-w-6xl",
  full: "max-w-[1600px]",
};

/**
 * App shell. Below the tablet breakpoint (768px) this is the original
 * phone-width column with the top bar and bottom navigation. At tablet widths
 * and up it switches to the sidebar shell from the desktop design and lets the
 * page content use the full width of the inset.
 */
export function Layout({
  children,
  width = "lg",
}: PropsWithChildren<{ width?: LayoutWidth }>) {
  const isTablet = useIsTablet();

  if (isTablet) {
    return (
      <DesktopLayout>
        <div className={cn("mx-auto w-full px-6 py-6", WIDTH_CLASSES[width])}>
          {children}
        </div>
      </DesktopLayout>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="relative mx-auto flex min-h-screen w-full max-w-md flex-col bg-background">
        <TopBar />
        <main className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto pb-40">
          {children}
        </main>
        <BottomNav />
      </div>
    </div>
  );
}
