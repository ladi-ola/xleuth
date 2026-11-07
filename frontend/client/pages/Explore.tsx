import { useState } from "react";
import { FigmaAppShell } from "@/components/figma/FigmaAppShell";
import { FigmaExploreView } from "@/components/figma/FigmaExploreView";
import type { BasketStatus } from "@/lib/market-data";
import { useBaskets, useBasketPrices } from "@/lib/api/hooks";
import { adaptBasket } from "@/lib/api/adapters";
import { usePageMeta } from "@/hooks/use-page-meta";

export default function Explore() {
  usePageMeta({
    title: "Explore index baskets — Xleuth (testnet)",
    description:
      "Browse active, upcoming and resolved prediction-market index baskets with live prices on the Amoy testnet.",
    path: "/explore",
  });
  const [tab, setTab] = useState<BasketStatus>("active");
  const [query, setQuery] = useState("");

  const { data: basketList, isPending, isError, refetch } = useBaskets();
  const basketOptions = basketList?.baskets ?? [];
  const prices = useBasketPrices(basketOptions.map((basket) => basket.basket_name));
  const baskets = basketOptions.map((basket, index) =>
    adaptBasket(basket, prices[index]?.data),
  );
  const search = query.trim().toLowerCase();
  const filtered = baskets.filter(
    (basket) =>
      basket.status === tab &&
      (basket.listName.toLowerCase().includes(search) ||
        basket.symbol.toLowerCase().includes(search)),
  );

  return (
    <FigmaAppShell>
      <FigmaExploreView
        tab={tab}
        onTabChange={setTab}
        query={query}
        onQueryChange={setQuery}
        baskets={filtered}
        isLoading={isPending}
        isError={isError}
        onRetry={() => { void refetch(); }}
      />
    </FigmaAppShell>
  );
}
