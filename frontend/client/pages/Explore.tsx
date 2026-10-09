import { useState } from "react";
import { Search } from "lucide-react";
import { Layout } from "@/components/xleuth/Layout";
import { SegmentedControl } from "@/components/xleuth/SegmentedControl";
import { MarketCard } from "@/components/xleuth/MarketCard";
import { EmptyState } from "@/components/xleuth/EmptyState";
import type { BasketStatus } from "@/lib/market-data";
import { useBaskets, useBasketPrices } from "@/lib/api/hooks";
import { adaptBasket } from "@/lib/api/adapters";
import { usePageMeta } from "@/hooks/use-page-meta";

export default function Explore() {
  usePageMeta({ title: 'Explore index baskets — Xleuth (testnet)', description: 'Browse active, upcoming and resolved prediction-market index baskets with live prices on the Amoy testnet.', path: '/explore' });
  const [tab, setTab] = useState<BasketStatus>("active");
  const [query, setQuery] = useState("");

  const { data: basketList } = useBaskets();
  const basketOptions = basketList?.baskets ?? [];
  const prices = useBasketPrices(basketOptions.map((b) => b.basket_name));

  const baskets = basketOptions.map((basket, index) => adaptBasket(basket, prices[index]?.data));

  const filtered = baskets.filter(
    (basket) =>
      basket.status === tab &&
      basket.listName.toLowerCase().includes(query.trim().toLowerCase()),
  );

  return (
    <Layout>
      <div className="flex flex-col gap-4 px-4 pt-4">
        <label className="flex h-10 items-center gap-2 rounded-lg border-[0.2px] border-neutral-600 bg-neutral-800 px-2">
          <Search className="h-4 w-4 p-0.5 text-neutral-500" strokeWidth={1.4} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search"
            className="w-full bg-transparent text-xs text-neutral-100 outline-none placeholder:text-neutral-500"
          />
        </label>

        <SegmentedControl
          value={tab}
          onChange={(v) => setTab(v as BasketStatus)}
          options={[
            { value: "active", label: "Active" },
            { value: "upcoming", label: "Upcoming" },
            { value: "resolved", label: "Resolved" },
          ]}
        />

        <div className="flex flex-col gap-2">
          {filtered.length > 0 ? (
            filtered.map((basket) => <MarketCard key={basket.slug} basket={basket} />)
          ) : (
            <EmptyState title="No markets found" caption="Try a different search or tab" />
          )}
        </div>
      </div>
    </Layout>
  );
}
