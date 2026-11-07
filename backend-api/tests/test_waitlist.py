from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from xleuth_api.main import create_app
from xleuth_api.db import Database, WAITLIST_TABLE_SQL, WAITLIST_STATUS_CHECK_SQL
from xleuth_api.waitlist_sync import sync_pending_entries


def make_client():
    app = create_app()
    app.state.db.pool = object()
    app.state.db.add_waitlist_entry = AsyncMock()
    return TestClient(app), app.state.db


def signup(**overrides):
    return {"name": " Ada Lovelace ", "email": " Ada@Example.com ",
            **overrides}


def test_normalizes_and_persists_signup():
    client, db = make_client()
    response = client.post("/waitlist", json=signup())
    assert response.status_code == 201
    assert response.json() == {"status": "ok"}
    db.add_waitlist_entry.assert_awaited_once_with("ada@example.com", "Ada Lovelace")


def test_duplicate_gets_identical_response():
    client, db = make_client()
    first = client.post("/waitlist", json=signup())
    second = client.post("/waitlist", json=signup())
    assert (first.status_code, first.json()) == (second.status_code, second.json())
    assert db.add_waitlist_entry.await_count == 2  # DB ON CONFLICT DO NOTHING


def test_bad_input_never_writes():
    for payload in (signup(email="bad"), signup(name="  "),
                    signup(name="x" * 101), signup(name="<script>"),
                    signup(email="a" * 250 + "@example.com")):
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
    assert [r.status_code for r in responses] == [201] * 5 + [429]
    assert responses[-1].headers["retry-after"]
    assert db.add_waitlist_entry.await_count == 5


def test_unavailable_database_does_not_claim_success():
    client, db = make_client()
    db.pool = None
    response = client.post("/waitlist", json=signup())
    assert response.status_code == 503
    db.add_waitlist_entry.assert_not_awaited()


def test_database_insert_failure_is_generic_and_retryable():
    client, db = make_client()
    db.add_waitlist_entry.side_effect = RuntimeError("private@example.com")
    response = client.post("/waitlist", json=signup())
    assert response.status_code == 503
    assert "private@example.com" not in response.text


def test_new_contract_does_not_require_consent_and_ignores_legacy_extra_field():
    client, db = make_client()
    response = client.post("/waitlist", json=signup(consent=True))
    assert response.status_code == 201
    db.add_waitlist_entry.assert_awaited_once()


def test_schema_supports_retryable_sync_states_and_unique_normalized_email():
    assert "email TEXT NOT NULL UNIQUE" in WAITLIST_TABLE_SQL
    assert "DEFAULT 'pending'" in WAITLIST_TABLE_SQL
    assert "sync_status IN ('pending', 'synced', 'failed')" in WAITLIST_STATUS_CHECK_SQL


def test_insert_is_idempotent_at_database_boundary():
    import asyncio

    class Connection:
        def __init__(self):
            self.rows = {}

        async def execute(self, query, email, name):
            assert "ON CONFLICT (email) DO NOTHING" in query
            self.rows.setdefault(email, name)

    class Acquire:
        async def __aenter__(self):
            return connection

        async def __aexit__(self, *_):
            pass

    class Pool:
        def acquire(self):
            return Acquire()

    connection = Connection()
    db = Database(None)
    db.pool = Pool()
    asyncio.run(db.add_waitlist_entry("ada@example.com", "Ada Lovelace"))
    asyncio.run(db.add_waitlist_entry("ada@example.com", "Ada Lovelace"))
    assert connection.rows == {"ada@example.com": "Ada Lovelace"}


def test_disabled_sync_keeps_database_only_signup_successful():
    import asyncio

    assert asyncio.run(sync_pending_entries()) == 0
    client, db = make_client()
    assert client.post("/waitlist", json=signup()).status_code == 201
    db.add_waitlist_entry.assert_awaited_once()
