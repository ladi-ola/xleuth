"""Safety regressions for source-timestamp freshness before oracle signing."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from xleuth_oracle.price_source import PostgresPriceSource, RedisPriceSource


@pytest.mark.asyncio
async def test_postgres_rejects_a_years_old_price():
    class Connection:
        async def fetchrow(self, query, basket_name):
            assert "scaled_price, ts" in query
            return {"scaled_price": 50.0, "ts": datetime(2020, 1, 1, tzinfo=timezone.utc)}

    class Acquisition:
        async def __aenter__(self):
            return Connection()

        async def __aexit__(self, *_):
            return None

    class Pool:
        def acquire(self):
            return Acquisition()

    source = PostgresPriceSource(None)
    source._pool = Pool()
    composite = __import__("xleuth_oracle.price_source", fromlist=["CompositePriceSource"]).CompositePriceSource([source])
    assert await composite.scaled_prices(["local-review-basket"]) == {"local-review-basket": None}


@pytest.mark.asyncio
async def test_redis_rejects_a_years_old_computed_at():
    class Client:
        async def get(self, channel):
            return json.dumps({"scaled_price": 50.0, "computed_at": "2020-01-01T00:00:00Z"})

    source = RedisPriceSource(None)
    source._client = Client()
    from xleuth_oracle.price_source import CompositePriceSource

    composite = CompositePriceSource([source])
    assert await composite.scaled_prices(["local-review-basket"]) == {"local-review-basket": None}


@pytest.mark.asyncio
async def test_redis_rejects_missing_or_future_timestamp():
    class Client:
        raw = json.dumps({"scaled_price": 50.0})

        async def get(self, channel):
            return self.raw

    source = RedisPriceSource(None)
    source._client = Client()
    from xleuth_oracle.price_source import CompositePriceSource

    composite = CompositePriceSource([source])
    assert await composite.scaled_prices(["basket"]) == {"basket": None}
    source._client.raw = json.dumps({
        "scaled_price": 50.0,
        "computed_at": (datetime.now(timezone.utc) + timedelta(seconds=120)).isoformat(),
    })
    assert await composite.scaled_prices(["basket"]) == {"basket": None}


@pytest.mark.asyncio
async def test_composite_falls_back_from_stale_db_to_fresh_redis():
    from xleuth_oracle.price_source import CompositePriceSource

    class Source:
        def __init__(self, sample):
            self.sample = sample
            self.max_staleness_seconds = 60

        async def scaled_price(self, name):
            return self.sample

    now = datetime.now(timezone.utc)
    composite = CompositePriceSource([
        Source((48.0, now - timedelta(hours=2))),
        Source((49.0, now)),
    ])
    assert await composite.scaled_prices(["basket"]) == {"basket": 49.0}


@pytest.mark.asyncio
@pytest.mark.parametrize("price", [float("nan"), float("inf"), 0, -1, 100.1])
async def test_composite_rejects_invalid_source_price(price):
    from xleuth_oracle.price_source import CompositePriceSource

    class Source:
        max_staleness_seconds = 60

        async def scaled_price(self, name):
            return price, datetime.now(timezone.utc)

    assert await CompositePriceSource([Source()]).scaled_prices(["basket"]) == {"basket": None}
