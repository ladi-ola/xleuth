import pytest

from xleuth_shared.order_intent import closing_intent, opening_intent


def test_canonical_opening_intent_has_five_words_and_unique_hash():
    intent, order_id = opening_intent("market", salt=b"\x11" * 32)
    assert len(intent) == 160
    assert intent[:31] == bytes(31)  # market = 1 is in the low byte
    assert intent[31] == 1
    assert intent[-32:] == b"\x11" * 32
    assert len(order_id) == 32
    assert order_id != opening_intent("market", salt=b"\x22" * 32)[1]


@pytest.mark.parametrize("kind,trigger", [("stop", 0), ("limit", 500), ("market", 1)])
def test_invalid_triggers_rejected(kind, trigger):
    with pytest.raises(ValueError):
        opening_intent(kind, salt=b"\x11" * 32, trigger_price=trigger)


def test_bracket_close_binds_lot_trigger_and_group():
    intent, order_id = closing_intent(
        "stop_loss", salt=b"\x11" * 32, position_id=(1).to_bytes(32, "big"),
        trigger_price=50_000, oco_group=b"\x22" * 32,
    )
    assert len(intent) == 160 and len(order_id) == 32
    assert intent[31] == 3
    assert intent[64:96] == b"\x22" * 32
    with pytest.raises(ValueError, match="OCO"):
        closing_intent(
            "take_profit", salt=b"\x11" * 32,
            position_id=(1).to_bytes(32, "big"), trigger_price=50_000,
        )
