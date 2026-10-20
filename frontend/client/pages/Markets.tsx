import { useState } from "react";
import { useParams } from "react-router-dom";
import { Eye, EyeOff } from "lucide-react";
import { useDynamicContext } from "@dynamic-labs/sdk-react-core";
import {
  useBaskets,
  useBasketPrice,
  useBasketConstituents,
  useCandles,
  useOrderBook,
  usePlaceOrder,
} from "@/lib/api/hooks";
import {
  adaptBasket,
  adaptCandles,
  adaptOrderBook,
  buildOrder,
} from "@/lib/api/adapters";
import { useToast } from "@/hooks/use-toast";
import { Layout } from "@/components/xleuth/Layout";
import { IndexHeader } from "@/components/xleuth/IndexHeader";
import { PriceChart } from "@/components/xleuth/PriceChart";
import { OrderBook } from "@/components/xleuth/OrderBook";
import { IndexDetailsCard } from "@/components/xleuth/IndexDetailsCard";
import { TradeButtons } from "@/components/xleuth/TradeButtons";
import {
  TradeModal,
  type TradeSubmission,
} from "@/components/xleuth/TradeModal";
import { OrderResultModal } from "@/components/xleuth/OrderResultModal";
import { SignInSheet } from "@/components/xleuth/SignInSheet";
import { SegmentedControl } from "@/components/xleuth/SegmentedControl";
import { EmptyState } from "@/components/xleuth/EmptyState";
import { usePageMeta } from "@/hooks/use-page-meta";
import { useIsTablet } from "@/hooks/use-media-query";

type Tab = "chart" | "order-book";
type Order = { side: "buy" | "sell"; amount: number; leverage: number };

function basketNameFromSlug(
  slug: string | undefined,
  baskets: { basket_name: string; slug?: string | null }[],
): string | undefined {
  if (!slug) return baskets[0]?.basket_name;
  // Prefer the API-provided slug (e.g. "top20-2026-10"), then fall back to the
  // name-derived form ("top20-october") used by older basket rows.
  const match = baskets.find(
    (basket) =>
      basket.slug === slug ||
      basket.basket_name.toLowerCase().replace(/_/g, "-") === slug,
  );
  // Task 13: unknown slugs resolve to undefined (distinct "unknown basket"
  // state) instead of silently falling back to the first basket.
  return match?.basket_name;
}

export default function Markets() {
  usePageMeta({
    title: "Xleuth — prediction-market index futures (testnet)",
    description:
      "Trade leveraged index futures on prediction-market baskets. Live prices, order book and 5x leverage on Polygon Amoy testnet.",
    path: "/",
  });
  const { slug } = useParams<{ slug?: string }>();
  const [tab, setTab] = useState<Tab>("chart");
  const [showOrderBook, setShowOrderBook] = useState(true);
  const [tradeSide, setTradeSide] = useState<"buy" | "sell" | null>(null);
  const [showSignIn, setShowSignIn] = useState(false);
  const [filledOrder, setFilledOrder] = useState<Order | null>(null);
  const { user } = useDynamicContext();
  const { toast } = useToast();
  const placeOrder = usePlaceOrder();
  const isTablet = useIsTablet();

  // Phase 3: public reads. Basket -> price -> candles/book/constituents.
  const { data: basketList, isLoading: basketsLoading } = useBaskets();
  const basketOptions = basketList?.baskets ?? [];
  const basketName = basketNameFromSlug(slug, basketOptions);
  const apiBasket = basketOptions.find((b) => b.basket_name === basketName);

  const { data: priceData } = useBasketPrice(basketName);
  const { data: candlesData } = useCandles(basketName, {
    interval: "15m",
    limit: 180,
  });
  const { data: orderBookData } = useOrderBook(basketName);
  const { data: constituentsData } = useBasketConstituents(basketName);

  if (basketsLoading) {
    return (
      <Layout>
        <EmptyState
          title="Loading markets"
          caption="Fetching live market data"
        />
      </Layout>
    );
  }

  if (!apiBasket || !basketName) {
    const unknownSlug = slug && basketOptions.length > 0;
    return (
      <Layout>
        <EmptyState
          title={
            unknownSlug ? `Unknown basket "${slug}"` : "Markets unavailable"
          }
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
  const attachProtectiveOrders = async (
    order: TradeSubmission,
    marketName: string,
  ) => {
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
      toast({
        title: "Market unavailable",
        description: "Basket data has not loaded yet.",
      });
      return;
    }
    if (!(order.amount > 0)) {
      toast({
        title: "Invalid size",
        description: "Enter an amount greater than 0.",
      });
      return;
    }
    if (order.orderType !== "limit" && !(order.slippageBps > 0)) {
      toast({
        title: "Slippage required",
        description: "Enter max slippage (bps) greater than 0.",
      });
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
        setFilledOrder({
          side: order.side,
          amount: order.amount,
          leverage: order.leverage,
        });
      } else if (
        response.status === "open" ||
        response.status === "partially_filled"
      ) {
        toast({
          title: `Order ${response.status.replace("_", " ")}`,
          description:
            "Your order is resting on the book. Track it in Portfolio.",
        });
      } else {
        toast({
          title: `Order ${response.status.replace("_", " ")}`,
          description:
            "The order did not fill. Check Portfolio for its current state.",
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
    <Layout width="full">
      {isTablet ? (
        <div className="@container flex w-full flex-col gap-5">
          <IndexHeader basket={basket} className="px-0 pt-0" />

          <div className="flex items-center justify-between gap-3">
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Chart
            </span>
            <button
              type="button"
              onClick={() => setShowOrderBook((visible) => !visible)}
              aria-pressed={showOrderBook}
              aria-controls="desktop-order-book"
              className="flex items-center gap-1.5 rounded-lg border-[0.4px] border-border bg-muted px-2.5 py-1.5 text-[10px] font-medium text-foreground/80 transition-colors hover:bg-muted hover:text-foreground"
            >
              {showOrderBook ? (
                <EyeOff className="h-3.5 w-3.5" strokeWidth={1.6} />
              ) : (
                <Eye className="h-3.5 w-3.5" strokeWidth={1.6} />
              )}
              {showOrderBook ? "Hide order book" : "Show order book"}
            </button>
          </div>

          <div className="flex flex-col gap-4 @min-[1000px]:flex-row @min-[1000px]:items-start">
            {/* Chart hero, with the trade ticket at its foot and the index
                details beneath. It grows into any space freed by hiding the
                order book. */}
            <div className="flex min-w-0 flex-1 flex-col gap-4">
              <PriceChart
                candles={candles}
                footer={
                  <div className="flex flex-col gap-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-foreground">
                        {basket.symbol}
                      </span>
                      <span className="text-[9px] font-light text-muted-foreground">
                        Amoy Testnet
                      </span>
                    </div>

                    <TradeButtons
                      variant="inline"
                      onSell={() => openTrade("sell")}
                      onBuy={() => openTrade("buy")}
                    />

                    <p className="text-center text-[9px] leading-[10px] text-muted-foreground">
                      Choose a side to open the order ticket.
                    </p>
                  </div>
                }
              />
              <IndexDetailsCard basket={basket} constituents={constituents} />
            </div>

            {/* Optional order book column. Hidden via the toggle above, which
                lets the chart reclaim the full width. It stacks below the
                chart until there is room for the two-column desktop layout. */}
            {showOrderBook ? (
              <aside
                id="desktop-order-book"
                aria-label="Order book"
                className="min-w-0 @min-[1000px]:sticky @min-[1000px]:top-5 @min-[1000px]:w-[320px] @min-[1000px]:flex-shrink-0 @min-[1240px]:w-[360px]"
              >
                <OrderBook
                  priceLabel={basket.priceLabel}
                  buys={orderBook?.buys}
                  sells={orderBook?.sells}
                />
              </aside>
            ) : null}
          </div>
        </div>
      ) : (
        <>
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

          <TradeButtons
            onSell={() => openTrade("sell")}
            onBuy={() => openTrade("buy")}
          />
        </>
      )}

      {tradeSide && (
        <TradeModal
          basket={basket}
          initialSide={tradeSide}
          onClose={() => setTradeSide(null)}
          onSubmitted={(order) => handleOrderSubmitted(order)}
        />
      )}

      {filledOrder && (
        <OrderResultModal
          basket={basket}
          order={filledOrder}
          onClose={() => setFilledOrder(null)}
        />
      )}

      {showSignIn && (
        <SignInSheet basket={basket} onClose={() => setShowSignIn(false)} />
      )}
    </Layout>
  );
}
