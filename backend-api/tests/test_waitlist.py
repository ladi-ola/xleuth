from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from xleuth_api.main import create_app


def make_client():
    app = create_app()
    app.state.db.pool = object()
    app.state.db.add_waitlist_entry = AsyncMock()
    return TestClient(app), app.state.db


def signup(**overrides):
    return {"name": " Ada Lovelace ", "email": " Ada@Example.com ",
            "consent": True, **overrides}


def test_normalizes_and_persists_signup():
    client, db = make_client()
    response = client.post("/waitlist", json=signup())
    assert response.status_code == 200
    db.add_waitlist_entry.assert_awaited_once_with("ada@example.com", "Ada Lovelace")


def test_duplicate_gets_identical_response():
    client, db = make_client()
    first = client.post("/waitlist", json=signup())
    second = client.post("/waitlist", json=signup())
    assert (first.status_code, first.json()) == (second.status_code, second.json())
    assert db.add_waitlist_entry.await_count == 2  # DB ON CONFLICT DO NOTHING


def test_bad_input_never_writes():
    for payload in (signup(email="bad"), signup(name="  "),
                    signup(name="x" * 121), signup(name="<script>"),
                    signup(consent=False), signup(email="a" * 250 + "@example.com")):
        client, db = make_client()
        assert client.post("/waitlist", json=payload).status_code == 422
        db.add_waitlist_entry.assert_not_awaited()


def test_validation_does_not_reflect_personal_data():
    client, _ = make_client()
    response = client.post("/waitlist", json=signup(name="<private-name>"))
    assert response.status_code == 422
    assert "private-name" not in response.text


def test_honeypot_does_not_store_or_reveal_itself():
    client, db = make_client()
    response = client.post("/waitlist", json=signup(website="spam.example"))
    comparison = client.post("/waitlist", json=signup())
    assert (response.status_code, response.json()) == (comparison.status_code, comparison.json())
    db.add_waitlist_entry.assert_awaited_once()


def test_rate_limit():
    client, db = make_client()
    responses = [client.post("/waitlist", json=signup()) for _ in range(6)]
    assert [r.status_code for r in responses] == [200] * 5 + [429]
    assert responses[-1].headers["retry-after"]
    assert db.add_waitlist_entry.await_count == 5


def test_unavailable_database_does_not_claim_success():
    client, db = make_client()
    db.pool = None
    response = client.post("/waitlist", json=signup())
    assert response.status_code == 503
    db.add_waitlist_entry.assert_not_awaited()
