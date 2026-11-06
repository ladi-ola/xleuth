from datetime import datetime, timezone

import pytest

from xleuth_ingestion.basket_builder import build_basket_from_params
from xleuth_ingestion.polymarket_client import PolymarketClient
from xleuth_ingestion.selection import select_constituents

START = datetime(2027, 1, 1, tzinfo=timezone.utc)
EXPIRY = datetime(2027, 2, 1, tzinfo=timezone.utc)


def market(identifier, end, volume=100):
    return {
        "id": identifier,
        "conditionId": identifier,
        "question": identifier,
        "endDate": end,
        "volumeNum": volume,
        "clobTokenIds": [identifier + "-yes", identifier + "-no"],
        "category": "politics",
    }


def test_january_2027_selection_is_year_qualified_and_half_open():
    markets = [
        market("old-january", "2026-01-10T00:00:00Z", 1_000_000),
        market("before", "2026-12-31T23:59:59Z", 1_000_000),
        market("start", "2027-01-01T00:00:00Z"),
        market("inside", "2027-01-31T23:59:59.999999Z"),
        market("at-expiry", "2027-02-01T00:00:00Z", 1_000_000),
        market("future-january", "2028-01-10T00:00:00Z", 1_000_000),
        market("invalid-date", "not a date", 1_000_000),
    ]
    selected, _ = select_constituents(
        markets, market_count=20, target_month=1,
        window_start=START, expiry_at=EXPIRY,
    )
    assert {m["id"] for m in selected} == {"start", "inside"}


def test_window_uses_real_instants_in_different_timezones():
    markets = [
        market("inside", "2027-01-01T01:00:00+01:00"),
        market("inside-offset", "2026-12-31T23:00:00-01:00"),
        market("outside", "2027-01-01T00:00:00+01:00"),
    ]
    selected, _ = select_constituents(
        markets, market_count=20, target_month=1,
        window_start=START, expiry_at=EXPIRY,
    )
    assert [m["id"] for m in selected] == ["inside", "inside-offset"]


def test_incomplete_or_reversed_window_is_rejected():
    with pytest.raises(ValueError):
        select_constituents([], market_count=20, target_month=1, window_start=START)
    with pytest.raises(ValueError):
        select_constituents(
            [], market_count=20, target_month=1,
            window_start=EXPIRY, expiry_at=START,
        )


class PriceClient:
    async def get_midpoints_batch(self, tokens):
        return {token: 0.5 for token in tokens}

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_builder_applies_the_same_window_before_computation(monkeypatch):
    async def volume_map(markets, client):
        return {m["conditionId"]: 100.0 for m in markets}

    monkeypatch.setattr("xleuth_ingestion.basket_builder.build_volume_map", volume_map)
    result = await build_basket_from_params(
        "TOP20-JANUARY", PriceClient(), market_count=20, target_month=1,
        window_start=START, expiry_at=EXPIRY,
        markets=[
            market("old", "2026-01-10T00:00:00Z", 1_000_000),
            market("new", "2027-01-10T00:00:00Z"),
        ],
    )
    assert result["total_constituents"] == 1
    assert result["constituents"][0]["condition_id"] == "new"
    assert result["index_price_scaled"] == 50.0


@pytest.mark.asyncio
async def test_public_client_can_be_constructed_by_admin_dry_run():
    # Before the fix, dry_run_report called PolymarketClient() but its three
    # URL arguments were mandatory, so no draft could be previewed.
    client = PolymarketClient()
    try:
        assert client.gamma_base == "https://gamma-api.polymarket.com"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_builder_never_substitutes_gamma_volume_for_missing_live_volume():
    with pytest.raises(ValueError, match="live_volume_unavailable"):
        await build_basket_from_params(
            "TOP20-JANUARY", PriceClient(), market_count=20, target_month=1,
            window_start=START, expiry_at=EXPIRY,
            markets=[market("new", "2027-01-10T00:00:00Z", 999999)],
        )
