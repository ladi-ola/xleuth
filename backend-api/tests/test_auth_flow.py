from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient
from web3 import Web3

w3 = Web3()


def test_auth_flow_full(client: TestClient):
    acct = w3.eth.account.create("test_wallet_for_xleuth_testing")
    wallet = acct.address

    resp = client.get(f"/auth/nonce/{wallet}")
    assert resp.status_code == 200
    nonce_data = resp.json()
    assert nonce_data["nonce"]
    assert nonce_data["wallet_address"] == wallet
    assert nonce_data["message"]

    message = nonce_data["message"]
    message_hash = encode_defunct(text=message)
    signed = w3.eth.account.sign_message(message_hash, private_key=acct.key)
    signature = signed.signature.hex()

    login_resp = client.post(
        "/auth/login",
        json={
            "wallet_address": wallet,
            "signature": signature,
            "message": message,
            "nonce": nonce_data["nonce"],
        },
    )
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    token_data = login_resp.json()
    assert token_data["access_token"]
    assert token_data["token_type"] == "Bearer"
    assert token_data["expires_in_minutes"] == 60
    print(f"\nAuth flow transcript:")
    print(f"  Wallet address: {wallet}")
    print(f"  Nonce: {nonce_data['nonce']}")
    print(f"  Signature: {signature[:64]}...")
    print(f"  JWT: {token_data['access_token'][:32]}...")

    me_resp = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    )
    assert me_resp.status_code == 200, f"/auth/me failed: {me_resp.text}"
    me_data = me_resp.json()
    assert me_data["wallet_address"] == wallet.lower()
    print(f"  Authenticated user: {me_data['wallet_address']}")

    bad_token_resp = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer invalid_token"},
    )
    assert bad_token_resp.status_code == 401


def test_auth_no_token(client: TestClient):
    resp = client.get("/auth/me")
    assert resp.status_code == 401

    resp = client.get("/accounts/me")
    assert resp.status_code == 401

    resp = client.get("/accounts/transactions")
    assert resp.status_code == 401


def test_auth_invalid_signature(client: TestClient):
    wallet = "0x1234567890123456789012345678901234567890"

    resp = client.get(f"/auth/nonce/{wallet}")
    assert resp.status_code == 200
    data = resp.json()

    login_resp = client.post(
        "/auth/login",
        json={
            "wallet_address": wallet,
            "signature": "0x" + "ab" * 65,
            "message": data["message"],
            "nonce": data["nonce"],
        },
    )
    assert login_resp.status_code == 401
