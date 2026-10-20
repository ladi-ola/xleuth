import { describe, it, expect } from "vitest";
import {
  adaptBasket,
  adaptPortfolioSummary,
  adaptPosition,
  adaptOpenOrder,
  adaptHistoryOrder,
  adaptTransaction,
  adaptCandles,
  adaptOrderBook,
  buildMarketOrder,
  buildOrder,
} from "./adapters";
import type {
  BasketInfo,
  BasketPriceResponseWithChange,
  PositionResponse,
  OrderListItem,
  TransactionInfo,
  CandlesResponse,
  BookSnapshot,
} from "./schemas";

const basket: BasketInfo = {
  basket_name: "TOP20-OCTOBER",
  total_constituents: 20,
  index_price: 23.91,
  index_price_scaled: 23.91,
  computed_at: "2026-10-09T12:00:00Z",
  status: "active",
  is_tradeable: true,
};

const price: BasketPriceResponseWithChange = {
  basket_name: "TOP20-OCTOBER",
  index_price: 23.91,
  scaled_price: 23.91,
  computed_at: "2026-10-09T12:00:00Z",
  constituent_count: 20,
  status: "active",
  is_tradeable: true,
  change_24h_abs: 0.89,
  change_24h_pct: 3.7,
};

describe("adaptBasket", () => {
  it("maps the API basket onto the component Basket shape", () => {
    const result = adaptBasket(basket, price);
    expect(result.slug).toBe("top20-october");
    expect(result.listName).toBe("TOP20-OCTOBER");
    expect(result.status).toBe("active");
    expect(result.price).toBe(23.91);
    expect(result.priceLabel).toBe("23.910\u00A2");
    expect(result.changeAbs).toBe(0.89);
    expect(result.changePct).toBe(3.7);
  });

  it("maps non-active statuses and tolerates a missing price", () => {
    const resolved = adaptBasket({ ...basket, status: "resolved" });
    expect(resolved.status).toBe("resolved");
    expect(resolved.price).toBe(23.91); // falls back to index_price_scaled
    expect(resolved.changeAbs).toBeNull();
    expect(resolved.changePct).toBeNull();
  });
});

describe("adaptPortfolioSummary", () => {
  it("maps balances and combines realized + unrealized PnL", () => {
    const result = adaptPortfolioSummary({
      total_balance: 1000,
      free_margin: 550,
      used_margin: 450,
      unrealized_pnl: 1250,
      realized_pnl: 7250,
    });
    expect(result).toEqual({
      totalBalance: 1000,
      freeMargin: 550,
      usedMargin: 450,
      unrealizedPnl: 1250,
      profitLoss: 8500,
    });
  });
});

describe("adaptPosition", () => {
  it("maps a long position and converts nulls to the placeholder values", () => {
    const pos: PositionResponse = {
      position_id: "0xabc_TOP20-OCTOBER",
      basket_name: "TOP20-OCTOBER",
      side: "buy",
      size: 410,
      leverage: 2,
      entry_price: 32.74,
      mark_price: 28.76,
      margin_usdc: 450,
      liquidation_price: null,
      unrealized_pnl_abs: -310.65,
      unrealized_pnl_pct: -17.1,
      stop_loss_price: null,
      take_profit_price: null,
      stop_loss_order_id: null,
      take_profit_order_id: null,
      oco_group_id: null,
      fee_paid: null,
      opened_at: "2026-10-07T13:54:17Z",
    };
    const result = adaptPosition(pos);
    expect(result.id).toBe("0xabc_TOP20-OCTOBER");
    expect(result.side).toBe("LONG");
    expect(result.leverage).toBe("2x Leverage");
    expect(result.liqPrice).toBe(0);
    expect(result.fee).toBe("\u2014");
    expect(result.openedAt).not.toBe("Unknown");
  });
});

describe("adaptOpenOrder", () => {
  it("derives side label and capitalises order type/status", () => {
    const order: OrderListItem = {
      order_id: "ord-1",
      basket_name: "TOP20-OCTOBER",
      side: "sell",
      order_type: "limit",
      price: 34.72,
      trigger_price: null,
      size: 250,
      filled_size: 0,
      remaining: 250,
      leverage: 2,
      status: "open",
      rejection_reason: null,
      created_at: "2026-10-05T19:43:22Z",
      updated_at: "2026-10-05T19:43:22Z",
      position_id: null,
      oco_group_id: null,
      average_fill_price: null,
    };
    const result = adaptOpenOrder(order);
    expect(result.side).toBe("Short");
    expect(result.orderType).toBe("Limit");
    expect(result.status).toBe("Open");
    expect(result.entry).toBe(34.72);
  });
});

describe("adaptHistoryOrder", () => {
  it("marks filled orders Completed", () => {
    const order = {
      order_id: "ord-2",
      basket_name: "TOP20-OCTOBER",
      side: "buy",
      order_type: "market",
      price: null,
      trigger_price: null,
      size: 250,
      filled_size: 250,
      remaining: 0,
      leverage: 2,
      status: "filled",
      rejection_reason: null,
      created_at: "2026-10-05T19:43:22Z",
      updated_at: "2026-10-05T19:44:00Z",
      position_id: null,
      oco_group_id: null,
      average_fill_price: 34.72,
    } as OrderListItem;
    const result = adaptHistoryOrder(order);
    expect(result.kind).toBe("trade");
    expect(result.status).toBe("Completed");
    if (result.kind === "trade") {
      expect(result.entry).toBe(34.72);
    }
  });
});

describe("adaptTransaction", () => {
  it("maps deposits to the transfer history variant", () => {
    const tx: TransactionInfo = {
      id: 7,
      wallet_address: "0xabc",
      tx_type: "deposit",
      amount: 10000,
      tx_hash: "0xdeadbeef",
      timestamp: "2026-10-05T19:43:22Z",
      related_position_id: null,
    };
    const result = adaptTransaction(tx);
    expect(result.kind).toBe("transfer");
    if (result.kind === "transfer") {
      expect(result.type).toBe("Deposit");
      expect(result.amount).toBe(10000);
      expect(result.status).toBe("Completed");
    }
  });
});

describe("buildMarketOrder", () => {
  it("translates USDC notional into contract size (notional ~= price x size)", () => {
    const request = buildMarketOrder({
      basketName: "TOP20-OCTOBER",
      side: "buy",
      notionalUsdc: 600,
      price: 30,
      leverage: 5,
      slippageBps: 100,
    });
    expect(request).toEqual({
      basket_name: "TOP20-OCTOBER",
      side: "buy",
      size: 20,
      leverage: 5,
      order_type: "market",
      max_slippage_bps: 100,
    });
  });

  it("returns zero size instead of dividing by a missing price", () => {
    const request = buildMarketOrder({
      basketName: "TOP20-OCTOBER",
      side: "sell",
      notionalUsdc: 600,
      price: 0,
      leverage: 2,
      slippageBps: 100,
    });
    expect(request.size).toBe(0);
  });
});

describe("buildOrder", () => {
  it("builds a limit order with the resting price and no slippage field", () => {
    const request = buildOrder({
      basketName: "TOP20-OCTOBER",
      side: "buy",
      orderType: "limit",
      notionalUsdc: 600,
      indexPrice: 30,
      leverage: 2,
      limitPrice: 29.5,
      slippageBps: 100,
    });
    expect(request).toEqual({
      basket_name: "TOP20-OCTOBER",
      side: "buy",
      size: 20,
      leverage: 2,
      order_type: "limit",
      price: 29.5,
    });
  });

  it("builds a stop order with trigger price and slippage guard", () => {
    const request = buildOrder({
      basketName: "TOP20-OCTOBER",
      side: "sell",
      orderType: "stop",
      notionalUsdc: 600,
      indexPrice: 30,
      leverage: 3,
      triggerPrice: 27.25,
      slippageBps: 150,
    });
    expect(request).toEqual({
      basket_name: "TOP20-OCTOBER",
      side: "sell",
      size: 20,
      leverage: 3,
      order_type: "stop",
      trigger_price: 27.25,
      max_slippage_bps: 150,
    });
  });

  it("does not send a size just below a whole unit through floating-point division", () => {
    // 738.67 / 73.867 evaluates to 9.999999999999998 without rounding; six
    // decimals keeps the derived size clean.
    const request = buildOrder({
      basketName: "TOP20-OCTOBER",
      side: "buy",
      orderType: "market",
      notionalUsdc: 738.67,
      indexPrice: 73.867,
      leverage: 2,
      slippageBps: 100,
    });
    expect(request.size).toBe(10);
  });

  it("builds a market order identical to buildMarketOrder", () => {
    const args = {
      basketName: "TOP20-OCTOBER",
      side: "buy" as const,
      notionalUsdc: 600,
      price: 30,
      leverage: 5,
      slippageBps: 100,
    };
    expect(
      buildOrder({
        basketName: args.basketName,
        side: args.side,
        orderType: "market",
        notionalUsdc: args.notionalUsdc,
        indexPrice: args.price,
        leverage: args.leverage,
        slippageBps: args.slippageBps,
      }),
    ).toEqual(buildMarketOrder(args));
  });
});

describe("adaptCandles / adaptOrderBook", () => {
  it("passes candle rows through unchanged", () => {
    const response: CandlesResponse = {
      basket_name: "TOP20-OCTOBER",
      interval: "15m",
      candles: [{ time: 1_760_000_000, open: 1, high: 2, low: 0.5, close: 1.5 }],
    };
    expect(adaptCandles(response)).toEqual(response.candles);
  });

  it("maps book levels into rows with a computed total", () => {
    const snapshot: BookSnapshot = {
      basket_name: "TOP20-OCTOBER",
      bids: [{ price: 43.5, size: 97 }],
      asks: [{ price: 48.1, size: 10 }],
      best_bid: 43.5,
      best_ask: 48.1,
      mid_price: 45.8,
      spread: 4.6,
      ts: "2026-10-09T12:00:00Z",
    };
    const result = adaptOrderBook(snapshot);
    expect(result.buys).toEqual([{ price: 43.5, amount: 97, total: 4219.5 }]);
    expect(result.sells).toEqual([{ price: 48.1, amount: 10, total: 481 }]);
  });
});
