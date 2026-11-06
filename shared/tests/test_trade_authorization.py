from dataclasses import replace
from decimal import Decimal

import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data

from xleuth_shared.trade_authorization import (
    MAX_NOTIONAL_UNITS,
    MIN_NOTIONAL_UNITS,
    UINT256_MAX,
    TradeAuthorization,
    exact_units,
    notional_units,
    price_units,
    size_units,
)

EXECUTOR = "0x" + "22" * 20
VECTOR_DIGEST = "dd4cdf2bedcadb6766b94138db28b3435cc8602f7cfe3efa8c97c4e1a4e877e7"


def authorization(**changes):
    base = TradeAuthorization(
        trader="0x" + "11" * 20,
        basket_id="0x" + "aa" * 32,
        order_id="0x" + "bb" * 32,
        side=0,
        size=1_234_567,
        max_notional=100_000_000,
        min_price=50_000,
        max_price=50_001,
        leverage=3,
        nonce=2**80 + 7,
        deadline=2_000_000_000,
    )
    return replace(base, **changes)


def test_eip712_vector_matches_browser_and_solidity():
    assert authorization().digest(80002, EXECUTOR).hex() == VECTOR_DIGEST


def test_trader_signs_without_relayer_knowing_trader_key():
    # Synthetic local key used only by this unit test's trader.
    trader = Account.from_key("0x" + "12" * 32)
    a = authorization(trader=trader.address)
    message = encode_typed_data(full_message=a.typed_data(80002, EXECUTOR))
    signature = trader.sign_message(message).signature
    assert Account.recover_message(message, signature=signature) == trader.address


@pytest.mark.parametrize("field,value", [
    ("trader", "0x" + "33" * 20),
    ("basket_id", "0x" + "cc" * 32),
    ("order_id", "0x" + "dd" * 32),
    ("side", 1),
    ("size", 1_234_568),
    ("max_notional", 100_000_001),
    ("min_price", 49_999),
    ("max_price", 50_002),
    ("leverage", 4),
    ("nonce", 7),
    ("deadline", 2_000_000_001),
    ("fill_or_kill", True),
    ("position_id", "0x" + "ee" * 32),
])
def test_every_signed_field_is_bound(field, value):
    original = authorization()
    changed = replace(original, **{field: value})
    assert changed.digest(80002, EXECUTOR) != original.digest(80002, EXECUTOR)


def test_reduce_only_flag_is_bound():
    a = authorization(position_id="0x" + "ee" * 32)
    assert replace(a, reduce_only=True).digest(80002, EXECUTOR) != a.digest(80002, EXECUTOR)


def test_chain_and_executor_are_bound():
    a = authorization()
    assert a.digest(80003, EXECUTOR) != a.digest(80002, EXECUTOR)
    assert a.digest(80002, "0x" + "33" * 20) != a.digest(80002, EXECUTOR)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "0", "1e1000000", "1e-1000000", "0.1234567", True, 0.1])
def test_invalid_size_input_is_rejected_without_rounding(value):
    with pytest.raises(ValueError):
        size_units(value)


def test_exact_units_and_notional():
    assert price_units("50.123") == 50_123
    assert size_units("0.200000") == 200_000
    assert notional_units(200_000, 50_123) == 10_024_600
    assert notional_units(1, 1) == 1  # Conservatively ceil one token base unit.
    assert notional_units(1, 1, round_up=False) == 0
    assert exact_units(Decimal("0.1234560000"), 6) == 123_456
    assert exact_units(str(UINT256_MAX), 0) == UINT256_MAX


def test_excess_price_precision_rejected():
    with pytest.raises(ValueError, match="precision"):
        price_units("50.1234")
    with pytest.raises(ValueError):
        price_units("100.001")


@pytest.mark.parametrize("value", [MIN_NOTIONAL_UNITS, MAX_NOTIONAL_UNITS])
def test_notional_budget_boundaries(value):
    assert authorization(max_notional=value).max_notional == value


@pytest.mark.parametrize("changes", [
    {"max_notional": MIN_NOTIONAL_UNITS - 1},
    {"max_notional": MAX_NOTIONAL_UNITS + 1},
    {"leverage": 6},
    {"side": True},
    {"nonce": -1},
    {"nonce": UINT256_MAX + 1},
    {"reduce_only": True},
    {"trader": "0x" + "00" * 20},
    {"basket_id": "0x" + "00" * 32},
    {"size": 0},
    {"min_price": 0},
    {"fill_or_kill": 1},
])
def test_invalid_authorization_rejected(changes):
    with pytest.raises(ValueError):
        authorization(**changes)
