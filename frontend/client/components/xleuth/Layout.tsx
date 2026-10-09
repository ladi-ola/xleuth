import { PropsWithChildren } from "react";
import { TopBar } from "./TopBar";
import { BottomNav } from "./BottomNav";

export function Layout({ children }: PropsWithChildren) {
  return (
    <div className="min-h-screen bg-neutral-950">
      <div className="relative mx-auto flex min-h-screen w-full max-w-md flex-col bg-neutral-950">
        <TopBar />
        <main className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto pb-40">{children}</main>
        <BottomNav />
      </div>
    </div>
  );
}
