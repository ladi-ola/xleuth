import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger("xleuth_ingestion.redis_publisher")


class RedisPublisher:
    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url
        self._client = None

    @property
    def enabled(self) -> bool:
        return self.redis_url is not None and self._client is not None

    async def connect(self) -> bool:
        if not self.redis_url:
            logger.info("No REDIS_URL set; Redis publishing disabled")
            return False
        try:
            import redis.asyncio as aioredis

            self._client = aioredis.from_url(self.redis_url, decode_responses=True)
            await self._client.ping()
            logger.info("Connected to Redis at %s", self.redis_url)
            return True
        except Exception:
            logger.warning("Redis unavailable; publishing disabled", exc_info=True)
            self._client = None
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    async def publish_basket(self, basket_result: dict) -> None:
        if not self.enabled:
            return
        channel = f"xleuth:basket:{basket_result['basket_name']}:price"
        payload = json.dumps(
            {
                "basket_name": basket_result["basket_name"],
                "index_price": basket_result.get("index_price"),
                "scaled_price": basket_result.get("index_price_scaled"),
                "computed_at": basket_result.get("computed_at", datetime.now(timezone.utc)).isoformat()
                if isinstance(basket_result.get("computed_at"), datetime)
                else basket_result.get("computed_at"),
                "constituent_count": basket_result.get("total_constituents"),
            },
            default=str,
        )
        try:
            await self._client.publish(channel, payload)
        except Exception:
            logger.warning("Failed to publish to Redis channel %s", channel, exc_info=True)

    @staticmethod
    def from_env() -> "RedisPublisher":
        host = os.getenv("REDIS_HOST", "localhost")
        port = os.getenv("REDIS_PORT", "6379")
        db = os.getenv("REDIS_DB", "0")
        redis_url = f"redis://{host}:{port}/{db}"
        return RedisPublisher(redis_url=redis_url)
