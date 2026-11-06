import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

from xleuth_ingestion.basket_builder import (
    build_basket,
    build_basket_from_params,
    _fetch_all_markets,
)
from xleuth_ingestion.polymarket_client import PolymarketClient
from xleuth_ingestion.redis_publisher import RedisPublisher
from xleuth_ingestion.storage import Storage
from xleuth_shared.basket_lifecycle import (
    STATUS_RESOLVED,
    BasketDescriptor,
    active_basket_names,
    expand_basket_templates,
    parse_basket_name,
)

logger = logging.getLogger("xleuth_ingestion")

# Guardrail hook (PLAN.md): fail fast if a retired basket-specific env var is
# still set. Nothing is retired yet — ACTIVE_BASKETS stays as fallback until
# the migrated rows are verified. Add names here in the final removal step.
RETIRED_BASKET_ENV_VARS: tuple[str, ...] = ()


def check_no_retired_env() -> None:
    stale = [v for v in RETIRED_BASKET_ENV_VARS if os.getenv(v)]
    if stale:
        raise RuntimeError(
            f"Retired basket env var(s) still set: {', '.join(stale)}. "
            "Baskets now live in the DB — unset these variables."
        )


def load_config() -> dict:
    load_dotenv()
    check_no_retired_env()
    return {
        "gamma_api_base": os.getenv("POLYMARKET_GAMMA_API_BASE", "https://gamma-api.polymarket.com"),
        "clob_api_base": os.getenv("POLYMARKET_CLOB_API_BASE", "https://clob.polymarket.com"),
        "data_api_base": os.getenv("POLYMARKET_DATA_API_BASE", "https://data-api.polymarket.com"),
        "database_url": os.getenv("DATABASE_URL"),
        "exclude_categories": os.getenv("EXCLUDE_CATEGORIES", "sports"),
        "active_baskets": os.getenv("ACTIVE_BASKETS", "TOP20-{MONTH}").split(","),
        "poll_interval": int(os.getenv("INGESTION_POLL_INTERVAL_SECONDS", "30")),
        "redis_url": os.getenv("REDIS_URL"),
    }


async def run_once(
    client: PolymarketClient,
    storage: Storage,
    config: dict,
    descriptors: list[BasketDescriptor],
) -> list[dict]:
    """Legacy entry: descriptors from ACTIVE_BASKETS templates (name-parsed)."""
    items = []
    for desc in descriptors:
        if desc.status == STATUS_RESOLVED:
            logger.info(
                "Basket %s is resolved; keeping history, not updating/trading",
                desc.basket_name,
            )
            continue
        parsed = parse_basket_name(desc.basket_name)
        if not parsed:
            logger.warning("Skipping undated/custom basket %s (no month/count in name)", desc.basket_name)
            continue
        n, target_month, _ = parsed
        items.append({
            "basket_name": desc.basket_name,
            "market_count": n,
            "target_month": target_month,
            "selection_rules": {},
            "source": "env",
        })
    return await run_once_items(client, storage, config, items)


async def discover_work_items(config: dict, pool) -> tuple[list[dict], list[BasketDescriptor]]:
    """DB-first discovery: active DB rows win; env templates fill the gap.

    Returns (items, descriptors) where items use explicit params (no parsing)
    and descriptors are the legacy env expansion (for stale-cleanup).
    A newly activated basket is picked up next cycle with no restart.
    """
    descriptors = expand_basket_templates(config["active_baskets"])
    items: list[dict] = []
    seen: set[str] = set()

    if pool is not None:
        try:
            from xleuth_shared.db_baskets import list_active

            for row in await list_active(pool):
                name = row["name"]
                exp = row["expiry_at"]
                from xleuth_shared.baskets import resolution_period_end

                month = resolution_period_end(exp).month
                items.append({
                    "basket_name": name,
                    "market_count": row["market_count"],
                    "target_month": month,
                    "selection_rules": row.get("selection_rules") or {},
                    "source": "db",
                    "slug": row["slug"],
                    "window_start": row["window_start"],
                    "expiry_at": exp,
                })
                seen.add(name)
        except Exception:
            logger.warning("DB basket discovery failed; using env only", exc_info=True)

    for desc in descriptors:
        if desc.basket_name in seen or desc.status == STATUS_RESOLVED:
            continue
        parsed = parse_basket_name(desc.basket_name)
        if not parsed:
            continue
        n, target_month, _ = parsed
        items.append({
            "basket_name": desc.basket_name,
            "market_count": n,
            "target_month": target_month,
            "selection_rules": {},
            "source": "env",
        })
        seen.add(desc.basket_name)
    return items, descriptors


async def run_once_items(
    client: PolymarketClient,
    storage: Storage,
    config: dict,
    items: list[dict],
) -> list[dict]:
    logger.info("Fetching all markets (single snapshot for all baskets)...")
    try:
        all_markets = await _fetch_all_markets(client)
        logger.info("Fetched %d markets across all pages", len(all_markets))
    except Exception:
        logger.exception("Market fetch failed, skipping this cycle")
        return []

    results = []
    for item in items:
        try:
            result = await build_basket_from_params(
                item["basket_name"],
                client=client,
                market_count=item["market_count"],
                target_month=item.get("target_month"),
                exclude_categories=config["exclude_categories"],
                selection_rules=item.get("selection_rules") or {},
                markets=all_markets,
                window_start=item.get("window_start"),
                expiry_at=item.get("expiry_at"),
            )
            await storage.save_basket(result)
            results.append(result)
            logger.info(
                "Basket %s [%s]: index_price=%.6f (scaled=%.2f), constituents=%d, excluded=%d",
                item["basket_name"],
                item.get("source", "?"),
                result["index_price"] or -1,
                result["index_price_scaled"] or -1,
                result["total_constituents"],
                result["markets_filtered_out"],
            )
        except Exception:
            logger.exception("Failed to build basket %s", item.get("basket_name"))
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
            items, descriptors = await discover_work_items(config, storage.pool)
            results = await run_once_items(client, storage, config, items)

            for result in results:
                await redis_pub.publish_basket(result)

            await storage.cleanup_stale_baskets([d.basket_name for d in descriptors])

            for result in results:
                await redis_pub.publish_basket(result)

            await storage.cleanup_stale_baskets([d.basket_name for d in descriptors])

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
