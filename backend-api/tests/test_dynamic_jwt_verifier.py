"""Tests for Dynamic.xyz JWT verification and wallet extraction.

These cover the claims/issuer shapes that Dynamic actually issues (which the
old verifier rejected): the issuer is ``app.dynamicauth.com/<env>`` (not
``.../environments/<env>``) and the wallet lives in ``verified_account`` /
``verified_credentials``, while ``sub`` is the Dynamic user id (a UUID).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from xleuth_shared.auth.dynamic_jwt import (
    DynamicJWTConfig,
    DynamicJWTError,
    DynamicJWTVerifier,
)

ENV_ID = "938a93a5-ee1f-4da2-86cf-27326bd01885"
WALLET = "0x" + "ab" * 20
OTHER_WALLET = "0x" + "cd" * 20
USER_ID = "d261ee91-8ea0-4949-b8bb-b6ab4f712a49"
KID = "274a96f7-0f11-4897-951f-3410a555bdcf"


def _jwk(private_key, kid: str = KID) -> dict:
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return jwk


class FakeVerifier(DynamicJWTVerifier):
    """Verifier whose JWKS is served from in-memory, scriptable key sets."""

    def __init__(self, batches: list):
        super().__init__(DynamicJWTConfig(environment_id=ENV_ID))
        # Accept either a single key set or a sequence of key sets (one per fetch).
        if batches and isinstance(batches[0], dict):
            batches = [batches]
        self._batches = [list(batch) for batch in batches]
        self.fetch_calls = 0

    def _fetch_jwks(self) -> dict:  # type: ignore[override]
        self.fetch_calls += 1
        if len(self._batches) > 1:
            return {"keys": self._batches.pop(0)}
        return {"keys": list(self._batches[0])}


@pytest.fixture
def keypair():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _token(private_key, claims: dict, kid: str = KID) -> str:
    now = datetime.now(timezone.utc)
    payload = {"iat": now, "exp": now + timedelta(minutes=5), **claims}
    return pyjwt.encode(payload, private_key, algorithm="RS256", headers={"kid": kid})


def test_accepts_current_issuer_and_verified_account(keypair):
    verifier = FakeVerifier([_jwk(keypair)])
    token = _token(
        keypair,
        {
            "iss": f"app.dynamicauth.com/{ENV_ID}",
            "environment_id": ENV_ID,
            "sub": USER_ID,
            "verified_account": {"address": WALLET, "chain": "EVM"},
        },
    )
    assert verifier.verify_token(token) == WALLET


def test_extracts_wallet_from_verified_credentials(keypair):
    verifier = FakeVerifier([_jwk(keypair)])
    token = _token(
        keypair,
        {
            "iss": f"https://app.dynamicauth.com/{ENV_ID}",
            "environment_id": ENV_ID,
            "sub": USER_ID,
            "verified_credentials": [
                {"address": "So11111111111111111111111111111111111111112", "chain": "SOL"},
                {"address": OTHER_WALLET, "chain": "EVM"},
            ],
        },
    )
    assert verifier.verify_token(token) == OTHER_WALLET


def test_never_treats_uuid_sub_as_wallet(keypair):
    verifier = FakeVerifier([_jwk(keypair)])
    token = _token(
        keypair,
        {
            "iss": f"app.dynamicauth.com/{ENV_ID}",
            "environment_id": ENV_ID,
            "sub": USER_ID,
        },
    )
    with pytest.raises(DynamicJWTError) as exc:
        verifier.verify_token(token)
    assert exc.value.code == "MISSING_WALLET_CLAIM"


def test_accepts_legacy_evm_address_in_sub(keypair):
    verifier = FakeVerifier([_jwk(keypair)])
    token = _token(
        keypair,
        {
            "iss": f"https://app.dynamicauth.com/environments/{ENV_ID}",
            "environment_id": ENV_ID,
            "sub": WALLET,
        },
    )
    assert verifier.verify_token(token) == WALLET


def test_rejects_token_from_another_environment(keypair):
    verifier = FakeVerifier([_jwk(keypair)])
    token = _token(
        keypair,
        {
            "iss": "app.dynamicauth.com/some-other-env",
            "environment_id": "some-other-env",
            "verified_account": {"address": WALLET},
        },
    )
    with pytest.raises(DynamicJWTError) as exc:
        verifier.verify_token(token)
    assert exc.value.code == "INVALID_ENVIRONMENT"


def test_refreshes_jwks_when_kid_rotates(keypair):
    rotated = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    new_kid = "rotated-kid"
    verifier = FakeVerifier(
        [
            [_jwk(keypair, KID)],
            [_jwk(keypair, KID), _jwk(rotated, new_kid)],
        ]
    )

    token = _token(
        rotated,
        {
            "iss": f"app.dynamicauth.com/{ENV_ID}",
            "environment_id": ENV_ID,
            "verified_account": {"address": WALLET},
        },
        kid=new_kid,
    )
    assert verifier.verify_token(token) == WALLET
    # First lookup missed the cached set, forcing one refresh.
    assert verifier.fetch_calls == 2


def test_expired_token(keypair):
    verifier = FakeVerifier([_jwk(keypair)])
    now = datetime.now(timezone.utc)
    token = pyjwt.encode(
        {
            "iss": f"app.dynamicauth.com/{ENV_ID}",
            "environment_id": ENV_ID,
            "verified_account": {"address": WALLET},
            "iat": now - timedelta(minutes=10),
            "exp": now - timedelta(minutes=5),
        },
        keypair,
        algorithm="RS256",
        headers={"kid": KID},
    )
    with pytest.raises(DynamicJWTError) as exc:
        verifier.verify_token(token)
    assert exc.value.code == "TOKEN_EXPIRED"


def test_rejects_bad_signature(keypair):
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = FakeVerifier([_jwk(keypair)])
    token = _token(
        attacker,
        {
            "iss": f"app.dynamicauth.com/{ENV_ID}",
            "environment_id": ENV_ID,
            "verified_account": {"address": WALLET},
        },
    )
    with pytest.raises(DynamicJWTError) as exc:
        verifier.verify_token(token)
    assert exc.value.code == "INVALID_SIGNATURE"
