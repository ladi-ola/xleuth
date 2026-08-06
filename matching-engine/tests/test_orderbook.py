import pytest

from xleuth_matching.orderbook import (
    BasketOrderBook,
    OrderBookManager,
    OrderRecord,
    OrderStatus,
    SelfTradeError,
    Side,
)


def _order(
    book: BasketOrderBook,
    trader: str,
    side: Side,
    price: float,
    size: float,
    leverage: int = 5,
    order_id: str | None = None,
) -> OrderRecord:
    return OrderRecord(
        order_id=order_id or f"o-{trader[:6]}-{side.value}-{price}",
        basket_name=book.basket_name,
        trader=trader,
        side=side,
        price=price,
        size=size,
        leverage=leverage,
    )


def test_crossing_orders_match_at_resting_price():
    book = BasketOrderBook("TOP20-AUGUST")
    maker = book.place(_order(book, "alice", Side.BUY, 48.0, 100.0))
    assert maker.order.status == OrderStatus.OPEN

    taker = book.place(_order(book, "bob", Side.SELL, 47.0, 100.0))
    assert taker.success
    assert len(taker.fills) == 1
    fill = taker.fills[0]
    assert fill.price == 48.0, "fill at resting (maker) price, price-time priority"
    assert fill.size == 100.0
    assert fill.taker_trader == "bob"
    assert fill.maker_trader == "alice"
    assert fill.taker_side is Side.SELL
    assert fill.maker_side is Side.BUY
    assert taker.order.status == OrderStatus.FILLED
    assert maker.order.status == OrderStatus.FILLED


def test_price_time_priority_fills_earliest_resting_order_first():
    book = BasketOrderBook("TOP20-AUGUST")
    a1 = book.place(_order(book, "alice", Side.BUY, 48.0, 100.0))
    a2 = book.place(_order(book, "carol", Side.BUY, 48.0, 100.0))
    assert a1.order.status == OrderStatus.OPEN
    assert a2.order.status == OrderStatus.OPEN

    taker = book.place(_order(book, "bob", Side.SELL, 47.0, 150.0))
    assert len(taker.fills) == 2
    assert taker.fills[0].maker_order_id == a1.order.order_id, "earlier order fills first"
    assert taker.fills[1].maker_order_id == a2.order.order_id
    assert a1.order.status == OrderStatus.FILLED
    assert a2.order.status == OrderStatus.PARTIALLY_FILLED
    assert a2.order.filled_size == 50.0
    assert taker.order.status == OrderStatus.FILLED


def test_partial_fill_rests_remainder_and_depth_reflects_it():
    book = BasketOrderBook("TOP20-AUGUST")
    book.place(_order(book, "alice", Side.BUY, 48.0, 100.0))
    taker = book.place(_order(book, "bob", Side.SELL, 47.0, 150.0))
    assert taker.order.status == OrderStatus.PARTIALLY_FILLED
    assert taker.order.remaining == 50.0

    bids, asks = book.depth()
    assert asks == [(47.0, 50.0)]
    assert bids == []
    snap = book.snapshot()
    assert snap["best_ask"] == 47.0
    assert snap["best_bid"] is None
    assert snap["mid_price"] == 47.0
    assert snap["spread"] is None


def test_non_crossing_orders_rest_and_snapshot_is_correct():
    book = BasketOrderBook("TOP20-AUGUST")
    book.place(_order(book, "alice", Side.BUY, 45.0, 100.0))
    book.place(_order(book, "bob", Side.SELL, 55.0, 100.0))
    bids, asks = book.depth()
    assert bids == [(45.0, 100.0)]
    assert asks == [(55.0, 100.0)]
    snap = book.snapshot()
    assert snap["best_bid"] == 45.0
    assert snap["best_ask"] == 55.0
    assert snap["mid_price"] == 50.0
    assert snap["spread"] == 10.0


def test_cancel_resting_order_removes_from_book():
    book = BasketOrderBook("TOP20-AUGUST")
    placed = book.place(_order(book, "alice", Side.BUY, 45.0, 100.0))
    book.cancel(placed.order.order_id)
    assert placed.order.status == OrderStatus.CANCELLED
    bids, _ = book.depth()
    assert bids == []


def test_cancel_filled_order_raises():
    book = BasketOrderBook("TOP20-AUGUST")
    maker = book.place(_order(book, "alice", Side.BUY, 48.0, 100.0))
    book.place(_order(book, "bob", Side.SELL, 47.0, 100.0))
    with pytest.raises(ValueError, match="cannot be cancelled"):
        book.cancel(maker.order.order_id)


def test_cancel_unknown_order_raises_keyerror():
    book = BasketOrderBook("TOP20-AUGUST")
    with pytest.raises(KeyError):
        book.cancel("nope")


def test_self_trade_guard_rejects_crossing_own_order():
    book = BasketOrderBook("TOP20-AUGUST")
    book.place(_order(book, "alice", Side.BUY, 48.0, 100.0))
    result = book.place(_order(book, "alice", Side.SELL, 47.0, 100.0))
    assert not result.success
    assert "self_trade" in result.error
    assert result.order.status == OrderStatus.REJECTED
    assert result.order.rejection_reason == result.error
    bids, asks = book.depth()
    assert bids == [(48.0, 100.0)], "book unchanged after rejected self-trade"
    assert asks == []


def test_self_trade_guard_allows_crossing_other_traders():
    book = BasketOrderBook("TOP20-AUGUST")
    book.place(_order(book, "alice", Side.BUY, 48.0, 100.0))
    result = book.place(_order(book, "bob", Side.SELL, 47.0, 100.0))
    assert result.success
    assert len(result.fills) == 1


def test_tick_size_fractional_prices():
    book = BasketOrderBook("TOP20-AUGUST")
    book.place(_order(book, "alice", Side.BUY, 45.12, 100.0))
    bids, _ = book.depth()
    assert bids == [(45.12, 100.0)]


def test_order_book_manager_keeps_one_book_per_basket():
    mgr = OrderBookManager(["TOP20-AUGUST", "TOP20-SEPTEMBER"])
    assert set(mgr.names()) == {"TOP20-AUGUST", "TOP20-SEPTEMBER"}
    b1 = mgr.get("TOP20-AUGUST")
    b2 = mgr.get("TOP20-AUGUST")
    assert b1 is b2
    b3 = mgr.get("TOP20-OCTOBER")
    assert b3 is not b1
    assert "TOP20-OCTOBER" in mgr.names()


def test_fill_notional_and_fee_property():
    book = BasketOrderBook("TOP20-AUGUST")
    book.place(_order(book, "alice", Side.BUY, 48.0, 100.0))
    result = book.place(_order(book, "bob", Side.SELL, 47.0, 100.0))
    fill = result.fills[0]
    assert fill.notional == 48.0 * 100.0
