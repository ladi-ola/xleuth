import pytest

from xleuth_ingestion.event_map import build_volume_map
from xleuth_ingestion.realized_fraction import compute_realized_fraction, _outcome_yes_price


class FakeClient:
    """Records every get_live_volume call; returns canned per-event payloads."""

    def __init__(self, volumes: dict[int, dict]):
        self.volumes = volumes
        self.calls: list[int] = []

    async def get_live_volume(self, event_id: int):
        self.calls.append(event_id)
        return self.volumes.get(event_id)


# ── Realized fraction ─────────────────────────────────────────────────


def test_outcome_yes_price_parses_resolved():
    # YES won
    assert _outcome_yes_price({"outcomePrices": "[0.5, 0.5]"}) == 0.0  # unresolved
    assert _outcome_yes_price({"outcomePrices": "[1, 0]"}) == 1.0
    assert _outcome_yes_price({"outcomePrices": "[0, 1]"}) == 0.0
    assert _outcome_yes_price({"outcomePrices": [1.0, 0.0]}) == 1.0
    assert _outcome_yes_price({"outcomePrices": [0.0, 1.0]}) == 0.0
    assert _outcome_yes_price({"outcomePrices": "garbage"}) == 0.0
    assert _outcome_yes_price({}) == 0.0


def test_compute_realized_fraction_basic():
    constituents = [
        {"conditionId": "0x1", "outcomePrices": "[1, 0]"},
        {"conditionId": "0x2", "outcomePrices": "[0, 1]"},
        {"conditionId": "0x3", "outcomePrices": "[1, 0]"},
    ]
    volume_map = {"0x1": 50.0, "0x2": 30.0, "0x3": 20.0}
    frac = compute_realized_fraction(constituents, volume_map)
    # (1*50 + 0*30 + 1*20) / (50+30+20) = 70/100 = 0.70
    assert abs(frac - 0.70) < 1e-9


def test_compute_realized_fraction_no_volume():
    assert compute_realized_fraction(
        [{"conditionId": "0x1", "outcomePrices": "[1, 0]"}], {}
    ) is None
    assert compute_realized_fraction([], {"0x1": 1.0}) is None


def test_compute_realized_fraction_missing_constituents_ignored():
    constituents = [
        {"conditionId": "0x1", "outcomePrices": "[1, 0]"},
        {"conditionId": "0xMISSING", "outcomePrices": "[1, 0]"},
    ]
    volume_map = {"0x1": 100.0}
    assert compute_realized_fraction(constituents, volume_map) == 1.0


# ── Dedup proof: two basket constituents in the SAME event ─────────────


@pytest.mark.asyncio
async def test_build_volume_map_dedups_shared_event():
    """Two markets (0xA, 0xB) both belong to the same parent event 99. The
    event's /live-volume payload lists each market once; the event must be
    queried exactly ONCE, and each constituent gets its own slice (not the
    event total wired to both)."""
    event_id = 99
    vol_data = {
        "markets": [
            {"market": "0x" + "A" * 64, "value": "900"},
            {"market": "0x" + "B" * 64, "value": "100"},
        ]
    }
    client = FakeClient({event_id: vol_data})

    def _event_market(cond_id: str):
        return {
            "conditionId": cond_id,
            "events": [{"id": event_id}],
        }

    markets = [
        _event_market("0x" + "A" * 64),
        _event_market("0x" + "B" * 64),
    ]

    volume_map = await build_volume_map(markets, client)

    assert client.calls == [event_id], "live-volume must be fetched once per event"
    assert volume_map == {"0x" + "A" * 64: 900.0, "0x" + "B" * 64: 100.0}


# NOTE: the above tests are pure/asyncio; ensure pytest-asyncio auto mode is on.