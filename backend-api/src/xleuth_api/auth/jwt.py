import logging
from datetime import datetime, timezone, timedelta

import jwt as pyjwt

logger = logging.getLogger("xleuth_api.auth.jwt")

ALGORITHM = "HS256"


class JWTHandler:
    def __init__(self, secret: str, expiry_minutes: int = 60):
        self.secret = secret
        self.expiry_minutes = expiry_minutes

    def issue_token(self, wallet_address: str) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": wallet_address,
            "iat": now,
            "exp": now + timedelta(minutes=self.expiry_minutes),
        }
        return pyjwt.encode(payload, self.secret, algorithm=ALGORITHM)

    def verify_token(self, token: str) -> str | None:
        try:
            payload = pyjwt.decode(token, self.secret, algorithms=[ALGORITHM])
            return payload.get("sub")
        except pyjwt.ExpiredSignatureError:
            logger.warning("JWT expired")
            return None
        except pyjwt.InvalidTokenError:
            logger.warning("Invalid JWT")
            return None
