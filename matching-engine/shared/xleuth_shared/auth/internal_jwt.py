"""Internal HS256 JWT verification for both backend-api and matching-engine.

Both services verify the same internal token issued by backend-api at /auth/verify.
The signing secret comes from the same env var (JWT_SECRET) in both services.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import jwt as pyjwt

logger = logging.getLogger("xleuth_shared.auth.internal_jwt")


@dataclass
class InternalJWTConfig:
    secret: str
    algorithm: str = "HS256"

    def __post_init__(self):
        if not self.secret or self.secret == "changeme-generate-a-real-256bit-secret":
            logger.warning("JWT_SECRET is using default value; set a real secret in production")


class InternalJWTError(Exception):
    """Raised when internal JWT verification fails."""

    def __init__(self, message: str, code: str = "INVALID_TOKEN"):
        super().__init__(message)
        self.code = code


class InternalJWTVerifier:
    """Verifies internal HS256 JWTs issued by backend-api."""

    def __init__(self, config: InternalJWTConfig):
        self.config = config

    def verify_token(self, token: str) -> str:
        """
        Verify an internal HS256 JWT and return the wallet address (lowercased).

        Raises:
            InternalJWTError: If token is missing, expired, or invalid.
        """
        if not token:
            raise InternalJWTError("Missing bearer token", "token_missing")

        try:
            payload = pyjwt.decode(
                token,
                self.config.secret,
                algorithms=[self.config.algorithm],
            )
        except pyjwt.ExpiredSignatureError:
            raise InternalJWTError("Token has expired", "token_expired")
        except pyjwt.InvalidSignatureError:
            raise InternalJWTError("Invalid token signature", "token_invalid")
        except pyjwt.InvalidTokenError as e:
            raise InternalJWTError(f"Invalid token: {e}", "token_invalid")

        wallet = payload.get("sub")
        if not wallet:
            raise InternalJWTError("Token missing 'sub' claim (wallet address)", "token_invalid")

        return wallet.lower()

    def verify_token_optional(self, token: Optional[str]) -> Optional[str]:
        """Verify token if provided, return None if missing or invalid (no exception)."""
        if not token:
            return None
        try:
            return self.verify_token(token)
        except InternalJWTError:
            return None