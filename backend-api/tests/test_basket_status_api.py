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


def test_closed_registry_status_is_normalized_to_resolved(app, monkeypatch):
    _patch_records(app, monkeypatch, [{
        "name": "TOP20-OCTOBER", "status": "closed", "expiry_at": FUTURE,
        "slug": "top20-2026-10", "onchain_index_id": "0xabc",
    }])
    _patch_price(app, monkeypatch, count=20, index_price=36.9, scaled_price=3690)

    basket = TestClient(app).get("/baskets").json()["baskets"][0]
    assert basket["status"] == "resolved"
    assert basket["is_tradeable"] is False


def test_registry_active_and_trading_is_active(app, monkeypatch):
    _patch_records(app, monkeypatch, [{
        "name": "TOP20-OCTOBER", "status": "active", "expiry_at": FUTURE,
        "slug": "top20-2026-10", "onchain_index_id": "0xabc",
    }])
    _patch_price(app, monkeypatch, count=20, index_price=36.9, scaled_price=3690)

    basket = TestClient(app).get("/baskets").json()["baskets"][0]
    assert basket["status"] == "active"
    assert basket["is_tradeable"] is True


def test_registry_active_but_not_trading_is_upcoming(app, monkeypatch):
    _patch_records(app, monkeypatch, [{
        "name": "TOP20-NOVEMBER", "status": "active", "expiry_at": FUTURE,
        "slug": "top20-2026-11", "onchain_index_id": "0xdef",
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
    # Earlier month -> Active; next month by name but seeded+trading -> Active;
    # no mapped markets -> Upcoming.
    assert by_name["TOP20-OCTOBER"]["status"] == "active"
    assert by_name["TOP20-NOVEMBER"]["status"] == "active"
    assert by_name["TOP20-DECEMBER"]["status"] == "upcoming"
