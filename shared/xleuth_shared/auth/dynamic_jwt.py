"""Dynamic.xyz JWT verification via JWKS.

Verifies JWTs issued by Dynamic.xyz against the environment's JWKS endpoint.
Extracts wallet address from verified token claims.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

import jwt as pyjwt
import requests
from jwt.algorithms import RSAAlgorithm

logger = logging.getLogger("xleuth_shared.auth.dynamic_jwt")


@dataclass
class DynamicJWTConfig:
    environment_id: str
    jwks_cache_ttl: int = 3600  # 1 hour

    @property
    def jwks_url(self) -> str:
        return f"https://app.dynamicauth.com/api/v0/sdk/{self.environment_id}/.well-known/jwks"

    @property
    def issuer(self) -> str:
        return f"https://app.dynamicauth.com/environments/{self.environment_id}"


class DynamicJWTError(Exception):
    """Raised when Dynamic JWT verification fails."""

    def __init__(self, message: str, code: str = "INVALID_TOKEN"):
        super().__init__(message)
        self.code = code


class DynamicJWTVerifier:
    """Verifies Dynamic.xyz JWTs using JWKS."""

    def __init__(self, config: DynamicJWTConfig):
        self.config = config
        self._jwks_cache: Optional[dict] = None
        self._cache_expiry: float = 0

    def _fetch_jwks(self) -> dict:
        """Fetch JWKS from Dynamic's endpoint."""
        try:
            response = requests.get(self.config.jwks_url, timeout=10)
            response.raise_for_status()
            jwks = response.json()
            if not jwks.get("keys"):
                raise DynamicJWTError("JWKS contains no keys", "JWKS_EMPTY")
            return jwks
        except requests.RequestException as e:
            logger.error("Failed to fetch JWKS from %s: %s", self.config.jwks_url, e)
            raise DynamicJWTError(f"JWKS fetch failed: {e}", "JWKS_FETCH_FAILED")

    def _get_jwks(self) -> dict:
        """Get JWKS with caching."""
        now = time.time()
        if self._jwks_cache is None or now >= self._cache_expiry:
            self._jwks_cache = self._fetch_jwks()
            self._cache_expiry = now + self.config.jwks_cache_ttl
        return self._jwks_cache

    def _get_public_key(self, kid: str) -> RSAAlgorithm:
        """Get RSA public key for the given key ID."""
        jwks = self._get_jwks()
        for key in jwks["keys"]:
            if key.get("kid") == kid:
                return RSAAlgorithm.from_jwk(key)
        raise DynamicJWTError(f"Key ID {kid} not found in JWKS", "KID_NOT_FOUND")

    def verify_token(self, token: str) -> str:
        """
        Verify a Dynamic JWT and return the wallet address (lowercased).

        Raises:
            DynamicJWTError: If token is invalid, expired, or malformed.
        """
        try:
            # Get unverified header to extract kid
            header = pyjwt.get_unverified_header(token)
            kid = header.get("kid")
            if not kid:
                raise DynamicJWTError("Token header missing 'kid'", "MISSING_KID")

            # Get public key
            public_key = self._get_public_key(kid)

            # Verify and decode token
            payload = pyjwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                issuer=self.config.issuer,
                options={"verify_aud": False},  # Dynamic doesn't use aud claim
            )

            # Extract wallet address from Dynamic's claims
            # Dynamic uses 'wallet_address' or 'sub' for wallet
            wallet = (
                payload.get("wallet_address")
                or payload.get("wallet")
                or payload.get("address")
                or payload.get("sub")
            )

            if not wallet:
                raise DynamicJWTError(
                    "Token missing wallet address claim (wallet_address, wallet, address, or sub)",
                    "MISSING_WALLET_CLAIM",
                )

            return wallet.lower()

        except pyjwt.ExpiredSignatureError:
            raise DynamicJWTError("Token has expired", "TOKEN_EXPIRED")
        except pyjwt.InvalidIssuerError:
            raise DynamicJWTError(f"Invalid issuer (expected {self.config.issuer})", "INVALID_ISSUER")
        except pyjwt.InvalidSignatureError:
            raise DynamicJWTError("Invalid token signature", "INVALID_SIGNATURE")
        except pyjwt.InvalidTokenError as e:
            raise DynamicJWTError(f"Invalid token: {e}", "INVALID_TOKEN")
        except DynamicJWTError:
            raise
        except Exception as e:
            logger.exception("Unexpected error verifying Dynamic JWT")
            raise DynamicJWTError(f"Verification failed: {e}", "VERIFICATION_ERROR")