from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from xleuth_shared.auth.dynamic_jwt import DynamicJWTError
from xleuth_shared.auth.internal_jwt import InternalJWTError, InternalJWTVerifier, InternalJWTConfig


class MockDynamicAuthHandler:
    """Mock Dynamic auth handler for testing."""
    
    def __init__(self):
        self.valid_tokens = {
            "valid-dynamic-token": "0x" + "a" * 40,
            "another-valid-token": "0x" + "b" * 40,
        }
        self.internal_secret = "test-secret"
        self.internal_expiry_minutes = 60
        self.internal_verifier = InternalJWTVerifier(InternalJWTConfig(secret=self.internal_secret))
    
    def verify_dynamic_token(self, token: str) -> str:
        if token in self.valid_tokens:
            return self.valid_tokens[token]
        raise DynamicJWTError("Invalid Dynamic token", "INVALID_TOKEN")
    
    def issue_internal_token(self, wallet_address: str) -> str:
        import jwt as pyjwt
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        payload = {
            "sub": wallet_address.lower(),
            "iat": now,
            "exp": now + timedelta(minutes=self.internal_expiry_minutes),
        }
        return pyjwt.encode(payload, self.internal_secret, algorithm="HS256")


def test_auth_flow_dynamic_verify(client: TestClient):
    """Test the new Dynamic JWT verification flow."""
    # The client fixture should have the mock auth handler
    # Verify Dynamic token -> get internal JWT
    dynamic_token = "valid-dynamic-token"
    
    resp = client.post(
        "/auth/verify",
        json={"token": dynamic_token},
    )
    assert resp.status_code == 200, f"Verify failed: {resp.text}"
    token_data = resp.json()
    assert token_data["access_token"]
    assert token_data["token_type"] == "Bearer"
    assert token_data["expires_in_minutes"] == 60
    
    # Use internal token to access /auth/me
    me_resp = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    )
    assert me_resp.status_code == 200, f"/auth/me failed: {me_resp.text}"
    me_data = me_resp.json()
    assert me_data["wallet_address"] == "0x" + "a" * 40


def test_auth_invalid_dynamic_token(client: TestClient):
    resp = client.post(
        "/auth/verify",
        json={"token": "invalid-dynamic-token"},
    )
    assert resp.status_code == 401


def test_auth_no_token(client: TestClient):
    resp = client.get("/auth/me")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "token_missing"

    resp = client.get("/accounts/me")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "token_missing"

    resp = client.get("/accounts/transactions")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "token_missing"


def test_auth_invalid_internal_token(client: TestClient):
    resp = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer invalid_internal_token"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "token_invalid"


def test_auth_expired_internal_token(client: TestClient):
    import jwt as pyjwt
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "0x" + "a" * 40,
        "iat": now - timedelta(minutes=120),
        "exp": now - timedelta(minutes=60),
    }
    expired_token = pyjwt.encode(payload, "test-secret", algorithm="HS256")
    
    resp = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "token_expired"