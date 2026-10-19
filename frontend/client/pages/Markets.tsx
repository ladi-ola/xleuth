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
import { adaptBasket, adaptCandles, adaptOrderBook, buildOrder } from "@/lib/api/adapters";
import { useToast } from "@/hooks/use-toast";
import { Layout } from "@/components/xleuth/Layout";
import { IndexHeader } from "@/components/xleuth/IndexHeader";
import { PriceChart } from "@/components/xleuth/PriceChart";
import { OrderBook } from "@/components/xleuth/OrderBook";
import { IndexDetailsCard } from "@/components/xleuth/IndexDetailsCard";
import { TradeButtons } from "@/components/xleuth/TradeButtons";
import { TradeModal, type TradeSubmission } from "@/components/xleuth/TradeModal";
import { OrderResultModal } from "@/components/xleuth/OrderResultModal";
import { SignInSheet } from "@/components/xleuth/SignInSheet";
import { SegmentedControl } from "@/components/xleuth/SegmentedControl";
import { EmptyState } from "@/components/xleuth/EmptyState";
import { usePageMeta } from "@/hooks/use-page-meta";

type Tab = "chart" | "order-book";
type Order = { side: "buy" | "sell"; amount: number; leverage: number };

function basketNameFromSlug(slug: string | undefined, basketNames: string[]): string | undefined {
  if (!slug) return basketNames[0];
  // Task 13: unknown slugs resolve to undefined (distinct "unknown basket"
  // state) instead of silently falling back to the first basket.
  return basketNames.find((name) => name.toLowerCase().replace(/_/g, "-") === slug);
}

export default function Markets() {
  usePageMeta({ title: 'Xleuth — prediction-market index futures (testnet)', description: 'Trade leveraged index futures on prediction-market baskets. Live prices, order book and 5x leverage on Polygon Amoy testnet.', path: '/' });
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
    const unknownSlug = slug && basketOptions.length > 0;
    return (
      <Layout>
        <EmptyState
          title={unknownSlug ? `Unknown basket "${slug}"` : "Markets unavailable"}
          caption={
            unknownSlug
              ? "It may have expired or never existed — see current baskets"
              : "Could not load markets"
          }
        />
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

  // Phase 6/7: Market, Limit and Stop entry orders are all supported by the
  // matching engine; the modal builds the type-specific price/trigger fields.
  // TP/SL are attached to an existing position (the API requires position_id
  // and cannot attach them to a brand-new entry). Rejections surface through
  // usePlaceOrder's mapped toasts; the modal closes on submit so resubmission
  // while a request is in flight is impossible.
  const attachProtectiveOrders = async (order: TradeSubmission, marketName: string) => {
    const ocoGroupId =
      order.takeProfit && order.stopLoss
        ? typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `${Date.now()}-${Math.random().toString(36).slice(2)}`
        : undefined;
    const maxSlippage = Math.max(1, Math.floor(order.slippageBps) || 100);
    const requests: Parameters<typeof placeOrder.mutateAsync>[0][] = [];
    if (order.stopLoss) {
      requests.push({
        order: {
          basket_name: marketName,
          order_type: "stop_loss",
          trigger_price: order.stopLoss,
          max_slippage_bps: maxSlippage,
          position_id: order.positionId,
          oco_group_id: ocoGroupId,
        },
      });
    }
    if (order.takeProfit) {
      requests.push({
        order: {
          basket_name: marketName,
          order_type: "take_profit",
          trigger_price: order.takeProfit,
          max_slippage_bps: maxSlippage,
          position_id: order.positionId,
          oco_group_id: ocoGroupId,
        },
      });
    }
    if (requests.length === 0) return;
    try {
      for (const request of requests) {
        await placeOrder.mutateAsync(request);
      }
      toast({
        title: "TP/SL set",
        description: "Protective orders attached to your position.",
      });
    } catch {
      // usePlaceOrder already toasted the failure.
    }
  };

  const handleOrderSubmitted = async (order: TradeSubmission) => {
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
    if (order.orderType !== "limit" && !(order.slippageBps > 0)) {
      toast({ title: "Slippage required", description: "Enter max slippage (bps) greater than 0." });
      return;
    }
    try {
      const response = await placeOrder.mutateAsync({
        order: buildOrder({
          basketName,
          side: order.side,
          orderType: order.orderType,
          notionalUsdc: order.amount,
          indexPrice: basket.price,
          leverage: order.leverage,
          slippageBps: Math.floor(order.slippageBps),
          limitPrice: order.limitPrice,
          triggerPrice: order.triggerPrice,
        }),
        idempotencyKey: order.idempotencyKey,
      });
      if (response.status === "filled") {
        setFilledOrder({ side: order.side, amount: order.amount, leverage: order.leverage });
      } else if (response.status === "open" || response.status === "partially_filled") {
        toast({
          title: `Order ${response.status.replace("_", " ")}`,
          description: "Your order is resting on the book. Track it in Portfolio.",
        });
      } else {
        toast({
          title: `Order ${response.status.replace("_", " ")}`,
          description: "The order did not fill. Check Portfolio for its current state.",
        });
      }
    } catch {
      // usePlaceOrder already toasted the mapped rejection/auth message. Do
      // not attach TP/SL when the entry order failed.
      return;
    }
    if (order.positionId && (order.takeProfit || order.stopLoss)) {
      await attachProtectiveOrders(order, basketName);
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
