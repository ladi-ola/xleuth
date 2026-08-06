import time

import pytest

from xleuth_matching.config import MatchingConfig
from xleuth_matching.margin_check import ChainState, MarginCheck
from xleuth_matching.orderbook import Side


def _now() -> int:
    return int(time.time())


class FakeChain(ChainState):
    def __init__(self, oracle=None, free=100_000.0, max_lev=5, pos=0):
        # oracle=None means "unreadable" (returns None); tests pass an
        # explicit (price, ts) tuple to simulate a readable oracle.
        self.oracle = oracle
        self.free = int(free * 1e6)
        self.max_lev = max_lev
        self.pos = pos
        self.position_reads = 0

    def oracle_price(self, basket_name):
        return self.oracle

    def free_balance(self, wallet):
        return self.free

    def max_leverage(self):
        return self.max_lev

    def position_size(self, wallet, basket_name):
        self.position_reads += 1
        return self.pos


NOW = _now()


def make_config(**overrides) -> MatchingConfig:
    base = dict(
        rpc_url="http://localhost:8545",
        vault_address="0x0000000000000000000000000000000000000001",
        position_manager_address="0x0000000000000000000000000000000000000002",
        oracle_consumer_address="0x0000000000000000000000000000000000000003",
        jwt_secret="test",
        chain_id=80002,
        price_scale=100,
        max_leverage=5,
        min_order_size=10,
        tick_size=0.01,
        trading_fee_bps=10,
        max_price_staleness_seconds=60,
        baskets=["TOP20-AUGUST", "TOP20-SEPTEMBER", "TOP20-JULY"],
        trader_keys={},
    )
    base.update(overrides)
    return MatchingConfig(**base)


def check(**kwargs):
    cfg = make_config()
    chain = FakeChain(oracle=(50, _now()))
    mc = MarginCheck(cfg, chain)
    return mc.validate(
        basket_name=kwargs.pop("basket_name", "TOP20-AUGUST"),
        wallet=kwargs.pop("wallet", "0xalice"),
        side=kwargs.pop("side", Side.BUY),
        price=kwargs.pop("price", 50.0),
        size=kwargs.pop("size", 100.0),
        leverage=kwargs.pop("leverage", 5),
    ), chain


def test_valid_order_passes():
    result, _ = check()
    assert result.ok, result.message
    assert result.details["oracle_price"] == 50
    assert result.details["required_usdc"] == 1000.0  # 50*100/5


def test_unknown_basket_rejected():
    result, _ = check(basket_name="TOP20-UNKNOWN")
    assert not result.ok
    assert result.reason == "unknown_basket"


def test_resolved_basket_rejected():
    result, _ = check(basket_name="TOP20-JULY")
    assert not result.ok
    assert result.reason == "basket_not_tradeable"


def test_price_out_of_range_rejected():
    result, _ = check(price=0.0)
    assert result.reason == "price_out_of_range"
    result, _ = check(price=101.0)
    assert result.reason == "price_out_of_range"


def test_price_not_on_tick_rejected():
    result, _ = check(price=50.005)
    assert result.reason == "price_not_on_tick"
    result, _ = check(price=50.01)
    assert result.ok


def test_size_below_min_rejected():
    result, _ = check(size=9.99)
    assert result.reason == "size_below_min"
    result, _ = check(size=10.0)
    assert result.ok


def test_leverage_out_of_range_rejected():
    result, _ = check(leverage=0)
    assert result.reason == "leverage_out_of_range"
    result, _ = check(leverage=6)
    assert result.reason == "leverage_out_of_range"


def test_leverage_above_live_cap_rejected():
    cfg = make_config(max_leverage=5)
    chain = FakeChain(oracle=(50, _now()), max_lev=4)
    mc = MarginCheck(cfg, chain)
    result = mc.validate("TOP20-AUGUST", "0xalice", Side.BUY, 50.0, 100.0, 5)
    assert not result.ok
    assert result.reason == "leverage_above_cap"
    assert result.details == {"requested": 5, "cap": 4}


def test_oracle_stale_rejected_with_age():
    result, _ = check()
    assert result.ok
    stale_chain = FakeChain(oracle=(50, NOW - 61))
    mc = MarginCheck(make_config(), stale_chain)
    result = mc.validate("TOP20-AUGUST", "0xalice", Side.BUY, 50.0, 100.0, 5)
    assert not result.ok
    assert result.reason == "oracle_price_stale"
    assert result.details["age_seconds"] >= 61


def test_oracle_unreadable_rejected():
    chain = FakeChain(oracle=None)
    mc = MarginCheck(make_config(), chain)
    result = mc.validate("TOP20-AUGUST", "0xalice", Side.BUY, 50.0, 100.0, 5)
    assert result.reason == "oracle_unreadable"


def test_oracle_zero_price_rejected():
    chain = FakeChain(oracle=(0, NOW))
    mc = MarginCheck(make_config(), chain)
    result = mc.validate("TOP20-AUGUST", "0xalice", Side.BUY, 50.0, 100.0, 5)
    assert result.reason == "oracle_price_zero"


def test_insufficient_margin_rejected_with_amounts():
    result, _ = check(size=100_000.0, leverage=5, price=90.0)
    assert not result.ok
    assert result.reason == "insufficient_margin"
    # required = oracle(50) * 100000 / 5 = 1,000,000 > free 100,000
    # (margin is computed from the on-chain ORACLE price, not the order price)
    assert result.details["required_usdc"] == 1_000_000.0
    assert result.details["free_usdc"] == 100_000.0
    assert result.details["oracle_price"] == 50


def test_margin_exact_boundary_passes():
    # required == free exactly: 50 * 10000 / 5 = 100,000
    result, _ = check(size=10_000.0, leverage=5, price=50.0)
    assert result.ok


def test_short_order_validated_same_rules():
    result, _ = check(side=Side.SELL)
    assert result.ok
