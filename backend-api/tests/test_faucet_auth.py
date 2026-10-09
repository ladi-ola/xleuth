"""Faucet claim auth tests: login-gated claims bound to the caller's wallet.

The success path is not covered here: it signs and broadcasts a real
Polygon Amoy transaction (needs OPERATOR_PRIVATE_KEY / RPC), so it is
verified end-to-end, not in unit tests.
"""

from fastapi.testclient import TestClient

ALICE = "0x" + "a" * 40
BOB = "0x" + "b" * 40


def _internal_token(client: TestClient, dynamic_token: str = "valid-dynamic-token") -> str:
    resp = client.post("/auth/verify", json={"token": dynamic_token})
    assert resp.status_code == 200, f"Verify failed: {resp.text}"
    return resp.json()["access_token"]


def test_faucet_claim_no_token_rejected(client: TestClient):
    resp = client.post("/faucet/claim", json={"smart_account_address": ALICE})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "token_missing"


def test_faucet_claim_invalid_token_rejected(client: TestClient):
    resp = client.post(
        "/faucet/claim",
        json={"smart_account_address": ALICE},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code == 401


def test_faucet_claim_other_wallet_rejected(client: TestClient):
    """An authenticated caller cannot direct funds to another address."""
    token = _internal_token(client)
    resp = client.post(
        "/faucet/claim",
        json={"smart_account_address": BOB},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_faucet_claim_invalid_address_rejected(client: TestClient):
    token = _internal_token(client)
    resp = client.post(
        "/faucet/claim",
        json={"smart_account_address": "not-an-address"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
