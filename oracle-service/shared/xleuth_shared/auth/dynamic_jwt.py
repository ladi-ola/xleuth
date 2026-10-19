"""Dynamic.xyz JWT verification via JWKS.

Verifies JWTs issued by Dynamic.xyz against the environment's JWKS endpoint
and extracts the wallet address from the verified claims.

Dynamic's JWTs carry the wallet in ``verified_account`` (the most recently
signed/verified blockchain account) or in ``verified_credentials`` /
``blockchain_accounts``. The ``sub`` claim is the Dynamic *user* id (a UUID),
not a wallet address, so it is only used when it actually looks like an EVM
address (older Dynamic tokens stored the wallet there).
"""

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

import jwt as pyjwt
import requests

logger = logging.getLogger("xleuth_shared.auth.dynamic_jwt")

# EVM wallet address: 0x followed by 40 hex characters.
_EVM_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")

# Sections of a Dynamic JWT that can carry blockchain account entries.
_ACCOUNT_SECTIONS = (
    "verified_credentials",
    "verifiedCredentials",
    "blockchain_accounts",
    "blockchainAccounts",
)


@dataclass
class DynamicJWTConfig:
    environment_id: str
    jwks_cache_ttl: int = 3600  # 1 hour

    @property
    def jwks_url(self) -> str:
        return f"https://app.dynamicauth.com/api/v0/sdk/{self.environment_id}/.well-known/jwks"

    @property
    def issuer(self) -> str:
        # Current Dynamic spelling (see https://www.dynamic.xyz/docs/auth/tokens).
        return f"https://app.dynamicauth.com/{self.environment_id}"

    @property
    def accepted_issuers(self) -> tuple[str, ...]:
        """Issuer spellings Dynamic has used across SDK/token versions.

        The signature is verified against the configured environment's JWKS and
        the ``environment_id`` claim is checked explicitly, so the exact issuer
        spelling is not security-critical. Accepting the known variants keeps
        both older and newer tokens working instead of 401-ing on a cosmetic
        difference in the ``iss`` claim.
        """
        env = self.environment_id
        return (
            f"https://app.dynamicauth.com/{env}",
            f"app.dynamicauth.com/{env}",
            f"https://app.dynamicauth.com/environments/{env}",
            f"app.dynamicauth.com/environments/{env}",
        )


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

    def _get_jwks(self, force_refresh: bool = False) -> dict:
        """Get JWKS with caching (optionally bypassing the cache)."""
        now = time.time()
        if force_refresh or self._jwks_cache is None or now >= self._cache_expiry:
            self._jwks_cache = self._fetch_jwks()
            self._cache_expiry = now + self.config.jwks_cache_ttl
        return self._jwks_cache

    @staticmethod
    def _find_key(jwks: dict, kid: str) -> Optional[dict]:
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                return key
        return None

    def _get_public_key(self, kid: str) -> Any:
        """Get the RSA public key for the given key ID.

        Dynamic rotates signing keys, so a cache miss on ``kid`` forces one
        refresh before giving up rather than 401-ing every request until the
        cache TTL expires.
        """
        jwks = self._get_jwks()
        key = self._find_key(jwks, kid)
        if key is None:
            logger.info("Dynamic kid %s not in cached JWKS; refreshing", kid)
            jwks = self._get_jwks(force_refresh=True)
            key = self._find_key(jwks, kid)
        if key is None:
            raise DynamicJWTError(f"Key ID {kid} not found in JWKS", "KID_NOT_FOUND")
        return pyjwt.PyJWK(key).key

    @staticmethod
    def _extract_wallet(payload: dict) -> Optional[str]:
        """Return the user's EVM wallet address from the token claims, if any."""
        candidates: list[Any] = []

        # Most recently signed/verified account (may be non-EVM; filtered below).
        for key in ("verified_account", "verifiedAccount"):
            account = payload.get(key)
            if isinstance(account, dict):
                candidates.append(account.get("address"))

        # All verified credentials / linked blockchain accounts.
        for section in _ACCOUNT_SECTIONS:
            entries = payload.get(section)
            if isinstance(entries, list):
                for entry in entries:
                    if isinstance(entry, dict):
                        candidates.append(entry.get("address"))

        # Legacy/deprecated claims.
        info = payload.get("info")
        if isinstance(info, dict):
            candidates.append(info.get("wallet") or info.get("walletAddress"))

        candidates.extend(
            (
                payload.get("wallet_address"),
                payload.get("walletAddress"),
                payload.get("wallet"),
                payload.get("address"),
            )
        )

        for candidate in candidates:
            if isinstance(candidate, str) and _EVM_ADDRESS_RE.match(candidate.strip()):
                return candidate.strip().lower()

        # ``sub`` is normally the Dynamic user id (UUID); accept it only if it
        # is genuinely an EVM address (older tokens used the wallet here).
        sub = payload.get("sub")
        if isinstance(sub, str) and _EVM_ADDRESS_RE.match(sub.strip()):
            return sub.strip().lower()

        return None

    def _validate_issuer(self, payload: dict) -> None:
        """Log (but do not reject on) an unexpected issuer spelling."""
        iss = payload.get("iss")
        if not isinstance(iss, str) or not iss:
            return
        normalized = iss.rstrip("/")
        if any(
            normalized == accepted.rstrip("/")
            or normalized.startswith(accepted.rstrip("/") + "/")
            for accepted in self.config.accepted_issuers
        ):
            return
        logger.warning(
            "Unexpected Dynamic JWT issuer %r (environment %s)",
            iss,
            self.config.environment_id,
        )

    def _validate_environment(self, payload: dict) -> None:
        """Reject tokens minted for another Dynamic environment."""
        token_env = payload.get("environment_id") or payload.get("environmentId")
        if token_env and token_env != self.config.environment_id:
            raise DynamicJWTError(
                "Token was issued for a different environment", "INVALID_ENVIRONMENT"
            )

    def verify_token(self, token: str) -> str:
        """
        Verify a Dynamic JWT and return the wallet address (lowercased).

        Raises:
            DynamicJWTError: If the token is invalid, expired, from another
                environment, or carries no wallet address.
        """
        try:
            # Get unverified header to extract kid
            header = pyjwt.get_unverified_header(token)
            kid = header.get("kid")
            if not kid:
                raise DynamicJWTError("Token header missing 'kid'", "MISSING_KID")

            # Get public key (refreshes JWKS on a kid cache miss)
            public_key = self._get_public_key(kid)

            # Verify the RS256 signature. The issuer is validated leniently
            # below because Dynamic has used more than one spelling.
            payload = pyjwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                options={"verify_aud": False, "verify_iss": False},
            )
        except pyjwt.ExpiredSignatureError:
            raise DynamicJWTError("Token has expired", "TOKEN_EXPIRED")
        except pyjwt.InvalidSignatureError:
            raise DynamicJWTError("Invalid token signature", "INVALID_SIGNATURE")
        except pyjwt.InvalidTokenError as e:
            raise DynamicJWTError(f"Invalid token: {e}", "INVALID_TOKEN")
        except DynamicJWTError:
            raise
        except Exception as e:
            logger.exception("Unexpected error verifying Dynamic JWT")
            raise DynamicJWTError(f"Verification failed: {e}", "VERIFICATION_ERROR")

        self._validate_issuer(payload)
        self._validate_environment(payload)

        wallet = self._extract_wallet(payload)
        if not wallet:
            raise DynamicJWTError(
                "Token has no EVM wallet address claim "
                "(verified_account, verified_credentials, blockchain_accounts)",
                "MISSING_WALLET_CLAIM",
            )

        return wallet
