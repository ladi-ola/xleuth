import { useState } from "react";
import { useParams } from "react-router-dom";
import { useDynamicContext } from "@dynamic-labs/sdk-react-core";
import {
  useBaskets,
  useBasketPrice,
  useBasketConstituents,
  useCandles,
  useOrderBook,
  usePlaceOrder,
} from "@/lib/api/hooks";
import { adaptBasket, adaptCandles, adaptOrderBook, buildMarketOrder } from "@/lib/api/adapters";
import { useToast } from "@/hooks/use-toast";
import { Layout } from "@/components/xleuth/Layout";
import { IndexHeader } from "@/components/xleuth/IndexHeader";
import { PriceChart } from "@/components/xleuth/PriceChart";
import { OrderBook } from "@/components/xleuth/OrderBook";
import { IndexDetailsCard } from "@/components/xleuth/IndexDetailsCard";
import { TradeButtons } from "@/components/xleuth/TradeButtons";
import { TradeModal } from "@/components/xleuth/TradeModal";
import { OrderResultModal } from "@/components/xleuth/OrderResultModal";
import { SignInSheet } from "@/components/xleuth/SignInSheet";
import { SegmentedControl } from "@/components/xleuth/SegmentedControl";
import { EmptyState } from "@/components/xleuth/EmptyState";

type Tab = "chart" | "order-book";
type Order = { side: "buy" | "sell"; amount: number; leverage: number };

function basketNameFromSlug(slug: string | undefined, basketNames: string[]): string | undefined {
  if (!slug) return basketNames[0];
  return basketNames.find((name) => name.toLowerCase().replace(/_/g, "-") === slug) ?? basketNames[0];
}

export default function Markets() {
  const { slug } = useParams<{ slug?: string }>();
  const [tab, setTab] = useState<Tab>("chart");
  const [tradeSide, setTradeSide] = useState<"buy" | "sell" | null>(null);
  const [showSignIn, setShowSignIn] = useState(false);
  const [filledOrder, setFilledOrder] = useState<Order | null>(null);
  const { user } = useDynamicContext();
  const { toast } = useToast();
  const placeOrder = usePlaceOrder();

  // Phase 3: public reads. Basket -> price -> candles/book/constituents.
  const { data: basketList, isLoading: basketsLoading } = useBaskets();
  const basketOptions = basketList?.baskets ?? [];
  const basketName = basketNameFromSlug(
    slug,
    basketOptions.map((b) => b.basket_name),
  );
  const apiBasket = basketOptions.find((b) => b.basket_name === basketName);

  const { data: priceData } = useBasketPrice(basketName);
  const { data: candlesData } = useCandles(basketName, { interval: "15m", limit: 180 });
  const { data: orderBookData } = useOrderBook(basketName);
  const { data: constituentsData } = useBasketConstituents(basketName);

  if (basketsLoading) {
    return (
      <Layout>
        <EmptyState title="Loading markets" caption="Fetching live market data" />
      </Layout>
    );
  }

  if (!apiBasket || !basketName) {
    return (
      <Layout>
        <EmptyState title="Markets unavailable" caption="Could not load markets" />
      </Layout>
    );
  }

  const basket = adaptBasket(apiBasket, priceData);
  const candles = candlesData ? adaptCandles(candlesData) : undefined;
  const orderBook = orderBookData ? adaptOrderBook(orderBookData) : undefined;
  const constituents = constituentsData?.constituents
    .map((c) => c.question)
    .filter((q): q is string => !!q);

  const openTrade = (side: "buy" | "sell") => {
    if (!user) {
      setShowSignIn(true);
      return;
    }
    setTradeSide(side);
  };

  // Phase 6: market-order placement. Only Market is enabled in the UI, so
  // only market orders are sent. Limit/Stop buttons are disabled in the modal
  // and stay unwired. Rejections surface through usePlaceOrder's mapped
  // toasts; the modal closes on submit (as before) so resubmission while a
  // request is in flight is impossible.
  const handleOrderSubmitted = async (order: {
    side: "buy" | "sell";
    amount: number;
    leverage: number;
    slippageBps: number;
  }) => {
    setTradeSide(null);
    if (!user) {
      setShowSignIn(true);
      return;
    }
    if (!basketName) {
      toast({ title: "Market unavailable", description: "Basket data has not loaded yet." });
      return;
    }
    if (!(order.amount > 0)) {
      toast({ title: "Invalid size", description: "Enter an amount greater than 0." });
      return;
    }
    if (!(order.slippageBps > 0)) {
      toast({ title: "Slippage required", description: "Enter max slippage (bps) greater than 0." });
      return;
    }
    try {
      const response = await placeOrder.mutateAsync(
        buildMarketOrder({
          basketName,
          side: order.side,
          notionalUsdc: order.amount,
          price: basket.price,
          leverage: order.leverage,
          slippageBps: Math.floor(order.slippageBps),
        }),
      );
      if (response.status === "filled") {
        setFilledOrder({ side: order.side, amount: order.amount, leverage: order.leverage });
      } else {
        toast({
          title: `Order ${response.status.replace("_", " ")}`,
          description: "The order did not fill. Check Portfolio for its current state.",
        });
      }
    } catch {
      // usePlaceOrder already toasted the mapped rejection/auth message.
    }
  };

  return (
    <Layout>
      <IndexHeader basket={basket} />

      <div className="mx-4 mt-5">
        <SegmentedControl
          value={tab}
          onChange={(v) => setTab(v as Tab)}
          options={[
            { value: "chart", label: "Chart" },
            { value: "order-book", label: "Order book" },
          ]}
          className="h-8 uppercase"
        />
      </div>

      <div className="mt-3 flex flex-col gap-3 px-4">
        {tab === "chart" ? (
          <PriceChart candles={candles} />
        ) : (
          <OrderBook
            priceLabel={basket.priceLabel}
            buys={orderBook?.buys}
            sells={orderBook?.sells}
          />
        )}
        <IndexDetailsCard basket={basket} constituents={constituents} />
      </div>

      <TradeButtons onSell={() => openTrade("sell")} onBuy={() => openTrade("buy")} />

      {tradeSide && (
        <TradeModal
          basket={basket}
          initialSide={tradeSide}
          onClose={() => setTradeSide(null)}
          onSubmitted={(order) => handleOrderSubmitted(order)}
        />
      )}

      {filledOrder && (
        <OrderResultModal basket={basket} order={filledOrder} onClose={() => setFilledOrder(null)} />
      )}

      {showSignIn && <SignInSheet basket={basket} onClose={() => setShowSignIn(false)} />}
    </Layout>
  );
}
