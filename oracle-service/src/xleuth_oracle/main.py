"""Oracle-service main loop: read price -> sign -> push on an interval."""

import asyncio
import logging
import os
import signal
import sys

from dotenv import load_dotenv

from xleuth_oracle.config import OracleConfig
from xleuth_oracle.price_source import (
    CompositePriceSource,
    PostgresPriceSource,
    RedisPriceSource,
)
from xleuth_oracle.pusher import Pusher

logger = logging.getLogger("xleuth_oracle")


async def run_cycle(pusher: Pusher, source: CompositePriceSource, config: OracleConfig) -> None:
    prices = await source.scaled_prices(config.baskets)
    for name, price in prices.items():
        if price is None:
            logger.warning("[%s] no price available this cycle", name)
    await pusher.push_all(prices)
    logger.info("Cycle complete for baskets=%s", config.baskets)


async def loop_forever(config: OracleConfig) -> None:
    pusher = Pusher(config)
    sources = CompositePriceSource([
        PostgresPriceSource(config.database_url),
        RedisPriceSource(config.redis_url),
    ])
    await sources.connect()
    try:
        # Push once immediately on boot, then on the interval.
        while True:
            try:
                await run_cycle(pusher, sources, config)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Cycle error; continuing")
            logger.info("Sleeping %ds until next push cycle", config.push_interval_seconds)
            await asyncio.sleep(config.push_interval_seconds)
    finally:
        await sources.close()


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