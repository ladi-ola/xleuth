import logging
import secrets
import time
from datetime import datetime, timezone

from eth_account.messages import encode_defunct
from web3 import Web3

logger = logging.getLogger("xleuth_api.auth.siwe")

SIWE_STATEMENT = "Sign in to Xleuth to access your account"
SIWE_VERSION = "1"
DOMAIN = "xleuth.app"


class SIWEHandler:
    def __init__(self, nonce_ttl: int = 300):
        self.nonce_ttl = nonce_ttl
        self._nonces: dict[str, dict] = {}
        self._w3 = Web3()

    def _clean_expired(self) -> None:
        now = time.time()
        expired = [k for k, v in self._nonces.items() if v["expires_at"] < now]
        for k in expired:
            del self._nonces[k]

    def generate_nonce(self, wallet_address: str) -> str:
        self._clean_expired()
        nonce = secrets.token_hex(16)
        self._nonces[nonce] = {
            "wallet_address": wallet_address.lower(),
            "created_at": time.time(),
            "expires_at": time.time() + self.nonce_ttl,
        }
        return nonce

    def build_message(self, wallet_address: str, nonce: str) -> str:
        issued_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        expiration = datetime.fromtimestamp(
            self._nonces.get(nonce, {}).get("expires_at", time.time()),
            tz=timezone.utc,
        ).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        lines = [
            f"{DOMAIN} wants you to sign in with your Ethereum account:",
            wallet_address,
            "",
            SIWE_STATEMENT,
            "",
            f"URI: http://localhost:3000",
            f"Version: {SIWE_VERSION}",
            f"Chain ID: 80002",
            f"Nonce: {nonce}",
            f"Issued At: {issued_at}",
            f"Expiration Time: {expiration}",
        ]
        return "\n".join(lines)

    def verify_signature(
        self, wallet_address: str, signature: str, message: str, nonce: str
    ) -> bool:
        self._clean_expired()
        nonce_data = self._nonces.pop(nonce, None)
        if nonce_data is None:
            logger.warning("Nonce not found or already used: %s...", nonce[:8])
            return False

        if nonce_data["wallet_address"] != wallet_address.lower():
            logger.warning(
                "Nonce wallet mismatch: expected %s, got %s",
                nonce_data["wallet_address"],
                wallet_address.lower(),
            )
            return False

        if nonce_data["expires_at"] < time.time():
            logger.warning("Nonce expired: %s...", nonce[:8])
            return False

        try:
            message_hash = encode_defunct(text=message)
            recovered = self._w3.eth.account.recover_message(message_hash, signature=signature)
            match = recovered.lower() == wallet_address.lower()
            if not match:
                logger.warning(
                    "Signature recovery mismatch: recovered %s, expected %s",
                    recovered,
                    wallet_address,
                )
            return match
        except Exception:
            logger.exception("Signature verification failed")
            return False
