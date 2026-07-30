import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

from xleuth_ingestion.basket_builder import build_basket, _fetch_all_markets
from xleuth_ingestion.polymarket_client import PolymarketClient
from xleuth_ingestion.redis_publisher import RedisPublisher
from xleuth_ingestion.storage import Storage

logger = logging.getLogger("xleuth_ingestion")


def load_config() -> dict:
    load_dotenv()
    return {
        "gamma_api_base": os.getenv("POLYMARKET_GAMMA_API_BASE", "https://gamma-api.polymarket.com"),
        "clob_api_base": os.getenv("POLYMARKET_CLOB_API_BASE", "https://clob.polymarket.com"),
        "data_api_base": os.getenv("POLYMARKET_DATA_API_BASE", "https://data-api.polymarket.com"),
        "database_url": os.getenv("DATABASE_URL"),
        "exclude_categories": os.getenv("EXCLUDE_CATEGORIES", "sports"),
        "active_baskets": os.getenv("ACTIVE_BASKETS", "TOP50-JULY,TOP50-AUGUST").split(","),
        "poll_interval": int(os.getenv("INGESTION_POLL_INTERVAL_SECONDS", "30")),
        "redis_url": os.getenv("REDIS_URL"),
    }


async def run_once(client: PolymarketClient, storage: Storage, config: dict) -> list[dict]:
    logger.info("Fetching all markets (single snapshot for all baskets)...")
    try:
        all_markets = await _fetch_all_markets(client)
        logger.info("Fetched %d markets across all pages", len(all_markets))
    except Exception:
        logger.exception("Market fetch failed, skipping this cycle")
        return []

    results = []
    for basket_name in config["active_baskets"]:
        basket_name = basket_name.strip()
        if not basket_name:
            continue
        try:
            result = await build_basket(
                basket_name,
                client=client,
                exclude_categories=config["exclude_categories"],
                markets=all_markets,
            )
            await storage.save_basket(result)
            results.append(result)
            logger.info(
                "Basket %s: index_price=%.6f (scaled=%.2f), constituents=%d, excluded=%d",
                basket_name,
                result["index_price"] or -1,
                result["index_price_scaled"] or -1,
                result["total_constituents"],
                result["markets_filtered_out"],
            )
        except Exception:
            logger.exception("Failed to build basket %s", basket_name)
    return results


async def polling_loop(config: dict) -> None:
    client = PolymarketClient(
        gamma_api_base=config["gamma_api_base"],
        clob_api_base=config["clob_api_base"],
        data_api_base=config["data_api_base"],
    )
    storage = Storage(config["database_url"])
    redis_pub = RedisPublisher(redis_url=config.get("redis_url"))

    try:
        db_ok = await storage.connect()
        if db_ok:
            await storage.ensure_schema()
            logger.info("Database connected and schema ensured.")

        await redis_pub.connect()

        while True:
            logger.info("Starting ingestion cycle...")
            results = await run_once(client, storage, config)

            for result in results:
                await redis_pub.publish_basket(result)

            await storage.cleanup_stale_baskets(config["active_baskets"])

            if not storage.pool:
                print(
                    json.dumps(
                        {
                            "ts": datetime.now(timezone.utc).isoformat(),
                            "baskets": results,
                        },
                        indent=2,
                        default=str,
                    )
                )

            logger.info("Sleeping %d seconds...", config["poll_interval"])
            await asyncio.sleep(config["poll_interval"])
    except asyncio.CancelledError:
        logger.info("Polling loop cancelled.")
    finally:
        await client.close()
        await storage.close()
        await redis_pub.close()


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = load_config()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    task = loop.create_task(polling_loop(config))

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, task.cancel)

    try:
        loop.run_until_complete(task)
    except asyncio.CancelledError:
        logger.info("Shutting down.")
    finally:
        loop.close()


if __name__ == "__main__":
    main()