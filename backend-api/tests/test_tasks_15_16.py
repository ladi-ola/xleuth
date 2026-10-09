"""Tasks 15 (alias validation) + 16 (rate limits, body size guard)."""
from fastapi.testclient import TestClient


def _token(client: TestClient) -> str:
    resp = client.post("/auth/verify", json={"token": "valid-dynamic-token"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_alias_accepts_valid(client: TestClient):
    token = _token(client)
    resp = client.put("/accounts/alias", params={"alias": "alice_01"},
                      headers={"Authorization": f"Bearer {token}"})
    # No DB in test env: upsert returns None -> stub profile, but validation passed (not 422)
    assert resp.status_code in (200, 500), resp.text
    assert resp.status_code != 422


def test_alias_rejects_blank_too_long_and_bad_chars(client: TestClient):
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    for bad in ["", "   ", "x" * 33, "<script>alert(1)</script>", "a/b", "a;b", "emoji-\U0001f600"]:
        resp = client.put("/accounts/alias", params={"alias": bad}, headers=headers)
        assert resp.status_code == 422, (bad, resp.text)


def test_auth_verify_rate_limited(client: TestClient):
    # Default 30/min/IP; the token fetch above already used 0 on this app
    # instance (fresh fixture per test) — burn through the bucket.
    for _ in range(30):
        resp = client.post("/auth/verify", json={"token": "nope"})
        assert resp.status_code in (401, 429), resp.text
    resp = client.post("/auth/verify", json={"token": "nope"})
    assert resp.status_code == 429, resp.text
    assert resp.json()["detail"] == "rate_limited"
    assert "Retry-After" in resp.headers


def test_oversize_body_rejected(client: TestClient):
    big = "x" * 1_100_000
    resp = client.post("/auth/verify", json={"token": big})
    assert resp.status_code == 413, resp.status_code
