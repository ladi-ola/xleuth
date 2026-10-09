"""Oracle-service main loop: read price -> sign -> push on an interval."""

import asyncio
import logging
import os
import signal
import sys

from dotenv import load_dotenv

from xleuth_oracle.config import OracleConfig
from xleuth_oracle.basket_source import discover_baskets
from xleuth_oracle.price_source import (
    CompositePriceSource,
    PostgresPriceSource,
    RedisPriceSource,
)
from xleuth_oracle.pusher import Pusher

logger = logging.getLogger("xleuth_oracle")


async def _db_pool(dsn: str | None):
    if not dsn:
        return None
    try:
        import asyncpg

        return await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    except Exception:
        logger.warning("Oracle DB pool unavailable; env fallback only", exc_info=True)
        return None


async def run_cycle(pusher: Pusher, source: CompositePriceSource, config: OracleConfig,
                    pool=None) -> None:
    # DB-first each cycle (short TTL inside); no restart needed for new baskets.
    baskets = await discover_baskets(config, pool)
    names = [b["name"] for b in baskets]
    index_ids = {b["name"]: b["index_id"] for b in baskets}
    prices = await source.scaled_prices(names)
    for name, price in prices.items():
        if price is None:
            logger.warning("[%s] no price available this cycle", name)
    await pusher.push_all(prices, index_ids)
    logger.info("Cycle complete for baskets=%s", names)


async def loop_forever(config: OracleConfig) -> None:
    pusher = Pusher(config)
    sources = CompositePriceSource([
        PostgresPriceSource(config.database_url),
        RedisPriceSource(config.redis_url),
    ])
    await sources.connect()
    pool = await _db_pool(config.database_url)
    try:
        # Push once immediately on boot, then on the interval.
        while True:
            try:
                await run_cycle(pusher, sources, config, pool)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Cycle error; continuing")
            logger.info("Sleeping %ds until next push cycle", config.push_interval_seconds)
            await asyncio.sleep(config.push_interval_seconds)
    finally:
        await sources.close()
        if pool is not None:
            await pool.close()


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    config = OracleConfig.load()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    task = loop.create_task(loop_forever(config))
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, task.cancel)
    try:
        loop.run_until_complete(task)
    except asyncio.CancelledError:
        logger.info("Oracle service shutting down.")
    finally:
        loop.close()


if __name__ == "__main__":
    main()