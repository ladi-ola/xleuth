"""Local-only evidence for JWT configuration and claim hardening findings.

These assertions describe the current vulnerability, not the desired fix.
The known example secret and synthetic account are NOT used on hosted APIs.
"""

import jwt

from xleuth_shared.auth.internal_jwt import InternalJWTConfig, InternalJWTVerifier


def test_evidence_example_secret_and_missing_expiry_are_accepted():
    config = InternalJWTConfig(secret="changeme-generate-a-real-256bit-secret")
    token = jwt.encode({"sub": "0x" + "1" * 40}, config.secret, algorithm="HS256")
    assert InternalJWTVerifier(config).verify_token(token) == "0x" + "1" * 40
