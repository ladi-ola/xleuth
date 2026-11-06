"""PLAN.md task 2: /baskets exposes the normalized section status.

The Explore page's Active/Upcoming/Resolved membership is decided in one place
(the backend status field) via xleuth_shared.basket_lifecycle.classify_index_status.
These tests pin the API surface: the status is always one of
active|upcoming|resolved (never a raw registry value like closed/settled), and
the seeded+trading rule drives Active vs Upcoming.
"""

from datetime import datetime, timezone
from functools import partial

import pytest
from fastapi.testclient import TestClient

FUTURE = datetime(2026, 11, 30, tzinfo=timezone.utc)
TS = datetime(2026, 10, 18, 3, 39, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _fixed_classification_time(monkeypatch):
    from xleuth_api.routes import baskets
    from xleuth_shared.basket_lifecycle import classify_index_status

    # These fixtures describe October 2026. Keep real lifecycle rules, but do
    # not let a later test-run date turn their active examples into history.
    monkeypatch.setattr(baskets, "classify_index_status", partial(classify_index_status, now=TS))


def _patch_price(app, monkeypatch, *, count, index_price, scaled_price):
    async def _latest(_name):
        return {
            "basket_name": "TOP20-X",
            "constituent_count": count,
            "index_price": index_price,
            "scaled_price": scaled_price,
            "ts": TS,
        }

    async def _24h(_name):
        return None

    monkeypatch.setattr(app.state.db, "get_latest_basket_price", _latest)
    monkeypatch.setattr(app.state.db, "get_price_24h_ago", _24h)


def _patch_records(app, monkeypatch, records):
    async def _records():
        return records

    monkeypatch.setattr(app.state.db, "list_basket_records", _records)


class ActiveRegistration:
    def __init__(self, expiry):
        self.expiry = int(expiry.timestamp())

    def settlement_state(self, _basket_id):
        return self.expiry, False


def test_closed_registry_status_is_normalized_to_resolved(app, monkeypatch):
    _patch_records(app, monkeypatch, [{
        "name": "TOP20-OCTOBER-2026", "status": "closed", "expiry_at": FUTURE,
        "slug": "top20-2026-10", "onchain_index_id": "0xabc",
    }])
    _patch_price(app, monkeypatch, count=20, index_price=36.9, scaled_price=3690)

    basket = TestClient(app).get("/baskets").json()["baskets"][0]
    assert basket["status"] == "resolved"
    assert basket["is_tradeable"] is False


def test_registry_active_and_trading_is_active(app, monkeypatch):
    from xleuth_shared.baskets import basket_id_from_slug

    slug = "top20-2026-10"
    _patch_records(app, monkeypatch, [{
        "name": "TOP20-OCTOBER-2026", "status": "active", "expiry_at": FUTURE,
        "slug": slug, "onchain_index_id": "0x" + basket_id_from_slug(slug).hex(),
    }])
    app.state.chain_reader = ActiveRegistration(FUTURE)
    _patch_price(app, monkeypatch, count=20, index_price=36.9, scaled_price=3690)

    basket = TestClient(app).get("/baskets").json()["baskets"][0]
    assert basket["status"] == "active"
    assert basket["is_tradeable"] is True


def test_registry_active_but_not_trading_is_upcoming(app, monkeypatch):
    _patch_records(app, monkeypatch, [{
        "name": "TOP20-NOVEMBER-2026", "status": "active", "expiry_at": FUTURE,
        "slug": "top20-2026-11", "onchain_index_id": "0x" + "de" * 32,
    }])

    async def _none(_name):
        return None

    async def _24h(_name):
        return None

    monkeypatch.setattr(app.state.db, "get_latest_basket_price", _none)
    monkeypatch.setattr(app.state.db, "get_price_24h_ago", _24h)

    basket = TestClient(app).get("/baskets").json()["baskets"][0]
    assert basket["status"] == "upcoming"
    assert basket["is_tradeable"] is False


def test_legacy_price_rows_drive_active_and_upcoming(app, monkeypatch):
    # Mirrors live data: no registry rows, baskets derive from index_prices.
    async def _empty():
        return []

    async def _rows():
        return [
            {"basket_name": "TOP20-OCTOBER", "constituent_count": 20,
             "index_price": 0.369, "scaled_price": 36.9, "ts": TS},
            {"basket_name": "TOP20-NOVEMBER", "constituent_count": 20,
             "index_price": 0.0022, "scaled_price": 0.22, "ts": TS},
            {"basket_name": "TOP20-DECEMBER", "constituent_count": 0,
             "index_price": None, "scaled_price": None, "ts": TS},
        ]

    async def _24h(_name):
        return None

    monkeypatch.setattr(app.state.db, "list_basket_records", _empty)
    monkeypatch.setattr(app.state.db, "list_baskets", _rows)
    monkeypatch.setattr(app.state.db, "get_price_24h_ago", _24h)

    by_name = {
        b["basket_name"]: b
        for b in TestClient(app).get("/baskets").json()["baskets"]
    }
    # Yearless names are ambiguous legacy labels; never assign the current
    # year or advertise them as tradable. History remains visible.
    assert by_name["TOP20-OCTOBER"]["status"] == "resolved"
    assert by_name["TOP20-NOVEMBER"]["status"] == "resolved"
    assert by_name["TOP20-DECEMBER"]["status"] == "resolved"
    assert all(not row["is_tradeable"] for row in by_name.values())


def test_year_qualified_fallback_has_expiry_and_slug_but_is_not_tradeable(app, monkeypatch):
    async def _empty():
        return []

    async def _rows():
        return [{"basket_name": "TOP20-APRIL-2027", "constituent_count": 20,
                 "index_price": 0.25, "scaled_price": 25.0, "ts": TS}]

    async def _24h(_name):
        return None

    monkeypatch.setattr(app.state.db, "list_basket_records", _empty)
    monkeypatch.setattr(app.state.db, "list_baskets", _rows)
    monkeypatch.setattr(app.state.db, "get_price_24h_ago", _24h)
    basket = TestClient(app).get("/baskets").json()["baskets"][0]
    assert basket["slug"] == "top20-2027-04"
    assert basket["expiry_at"] in ("2027-05-01T00:00:00Z", "2027-05-01T00:00:00+00:00")
    assert basket["is_tradeable"] is False


def test_legacy_yearless_fallback_uses_settlement_expiry(app, monkeypatch):
    async def _empty():
        return []

    async def _rows():
        return [{"basket_name": "TOP20-NOVEMBER", "constituent_count": 20,
                 "index_price": 0.2, "scaled_price": 20.0, "ts": TS}]

    async def _24h(_name):
        return None

    class Chain:
        @staticmethod
        def basket_id(_name):
            return b"legacy-id"

        @staticmethod
        def settlement_state(_basket_id):
            return (1786238371, True)

    app.state.chain_reader = Chain()
    monkeypatch.setattr(app.state.db, "list_basket_records", _empty)
    monkeypatch.setattr(app.state.db, "list_baskets", _rows)
    monkeypatch.setattr(app.state.db, "get_price_24h_ago", _24h)
    basket = TestClient(app).get("/baskets").json()["baskets"][0]
    assert basket["basket_name"] == "TOP20-NOVEMBER"  # preserve legacy alias
    assert basket["expiry_at"] == "2026-08-09T01:19:31Z"
    assert basket["status"] == "resolved"
    assert basket["is_tradeable"] is False
