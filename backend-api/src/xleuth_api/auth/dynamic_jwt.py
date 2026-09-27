"""Dynamic.xyz JWT verification and internal token issuance for backend-api."""

import logging
from datetime import datetime, timezone, timedelta

import jwt as pyjwt

from xleuth_shared.auth.dynamic_jwt import (
    DynamicJWTConfig,
    DynamicJWTVerifier,
    DynamicJWTError,
)

logger = logging.getLogger("xleuth_api.auth.dynamic_jwt")

ALGORITHM = "HS256"


class DynamicAuthHandler:
    """Handles Dynamic JWT verification and internal token issuance."""

    def __init__(
        self,
        environment_id: str,
        internal_jwt_secret: str,
        internal_jwt_expiry_minutes: int = 60,
        jwks_cache_ttl: int = 3600,
    ):
        self.config = DynamicJWTConfig(
            environment_id=environment_id,
            jwks_cache_ttl=jwks_cache_ttl,
        )
        self.verifier = DynamicJWTVerifier(self.config)
        self.internal_secret = internal_jwt_secret
        self.internal_expiry_minutes = internal_jwt_expiry_minutes

    def verify_dynamic_token(self, token: str) -> str:
        """
        Verify a Dynamic.xyz JWT and return the wallet address.

        Raises:
            DynamicJWTError: If token is invalid.
        """
        return self.verifier.verify_token(token)

    def issue_internal_token(self, wallet_address: str) -> str:
        """Issue an internal HS256 JWT for use with matching-engine."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": wallet_address.lower(),
            "iat": now,
            "exp": now + timedelta(minutes=self.internal_expiry_minutes),
        }
        return pyjwt.encode(payload, self.internal_secret, algorithm=ALGORITHM)

    def verify_internal_token(self, token: str) -> str | None:
        """Verify an internal HS256 JWT and return wallet address."""
        try:
            payload = pyjwt.decode(token, self.internal_secret, algorithms=[ALGORITHM])
            return payload.get("sub")
        except pyjwt.ExpiredSignatureError:
            logger.warning("Internal JWT expired")
            return None
        except pyjwt.InvalidTokenError:
            logger.warning("Invalid internal JWT")
            return None