"""Issue 1/2 regression tests: candles endpoint + CORS on unhandled errors."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient


def test_candles_unsupported_interval_returns_400(client: TestClient):
    resp = client.get("/baskets/TOP20-NOVEMBER/candles?interval=bogus")
    assert resp.status_code == 400
    assert "unsupported_interval" in resp.json()["detail"]


def test_candles_unknown_basket_returns_404(client: TestClient):
    # No database is configured in tests, so no basket is known.
    resp = client.get("/baskets/DOES-NOT-EXIST/candles")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "basket_not_found"


def test_candles_known_basket_with_no_data_returns_200_empty(app, monkeypatch):
    async def _exists(_name: str) -> bool:
        return True

    async def _empty(*_args, **_kwargs):
        return []

    monkeypatch.setattr(app.state.db, "basket_exists", _exists)
    monkeypatch.setattr(app.state.db, "get_candles", _empty)

    client = TestClient(app)
    resp = client.get("/baskets/TOP20-NOVEMBER/candles?interval=15m&limit=180")
    assert resp.status_code == 200
    body = resp.json()
    assert body["basket_name"] == "TOP20-NOVEMBER"
    assert body["candles"] == []


def test_candles_returns_buckets(app, monkeypatch):
    async def _exists(_name: str) -> bool:
        return True

    async def _rows(*_args, **_kwargs):
        return [
            {
                "bucket": datetime(2026, 10, 18, 1, 0, tzinfo=timezone.utc),
                "open": 0.20,
                "high": 0.22,
                "low": 0.19,
                "close": 0.21,
            }
        ]

    monkeypatch.setattr(app.state.db, "basket_exists", _exists)
    monkeypatch.setattr(app.state.db, "get_candles", _rows)

    client = TestClient(app)
    resp = client.get("/baskets/TOP20-NOVEMBER/candles?interval=15m")
    assert resp.status_code == 200
    candles = resp.json()["candles"]
    assert len(candles) == 1
    assert candles[0]["open"] == 0.20
    assert candles[0]["close"] == 0.21
    # time is unix seconds derived from the bucket timestamp
    assert candles[0]["time"] == int(
        datetime(2026, 10, 18, 1, 0, tzinfo=timezone.utc).timestamp()
    )


def test_unhandled_error_returns_json_500_with_cors(app):
    async def _boom():
        raise RuntimeError("boom")

    app.get("/__boom")(_boom)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/__boom", headers={"Origin": "https://www.xleuth.xyz"})
    assert resp.status_code == 500
    assert resp.headers.get("content-type", "").startswith("application/json")
    assert resp.json()["detail"] == "Internal Server Error"
    # The 500 must still carry CORS headers (browser must not report CORS).
    assert resp.headers.get("access-control-allow-origin") == "https://www.xleuth.xyz"


def test_both_production_origins_allowed(app):
    client = TestClient(app)
    for origin in ("https://xleuth.xyz", "https://www.xleuth.xyz"):
        resp = client.get("/baskets", headers={"Origin": origin})
        assert resp.headers.get("access-control-allow-origin") == origin
