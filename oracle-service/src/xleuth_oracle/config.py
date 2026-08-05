"""Oracle-service configuration, read from environment variables (.env).

Required:
  POLYGON_AMOY_RPC_URL / RPC_URL
  INDEX_ORACLE_CONSUMER_ADDRESS
  ORACLE_SIGNER_PRIVATE_KEY   (or DEPLOYER_PRIVATE_KEY fallback)
  CHAIN_ID

Optional (defaults shown):
  ORACLE_PUSH_INTERVAL_SECONDS=15
  ORACLE_MAX_PRICE_STALENESS_SECONDS=60
  ORACLE_RETRY_MAX_ATTEMPTS=5
  ORACLE_RETRY_BACKOFF_SECONDS=2
  INDEX_PRICE_SCALE=100
  ACTIVE_BASKETS=TOP20-{MONTH}
  DATABASE_URL (if reading from Postgres)
  REDIS_URL    (if reading the live stream)

Prices read from data-ingestion are floats; on-chain prices must be integers in
[1, priceScale]. `round_to_scale` is applied before signing.
"""

import os
from dataclasses import dataclass, field

from xleuth_shared.basket_lifecycle import active_basket_names


@dataclass(frozen=True)
class OracleConfig:
    rpc_url: str
    contract_address: str
    signer_private_key: str
    signer_address: str
    chain_id: int
    price_scale: int
    max_staleness: int
    push_interval_seconds: int
    retry_max_attempts: int
    retry_backoff_seconds: int
    baskets: list[str] = field(default_factory=list)
    database_url: str | None = None
    redis_url: str | None = None

    @staticmethod
    def _addr(key: str) -> str:
        value = os.getenv(key, "").strip()
        if not value:
            raise ValueError(f"Missing required env var {key}")
        if not value.startswith("0x"):
            value = "0x" + value
        return value

    @staticmethod
    def load() -> "OracleConfig":
        from eth_account import Account

        rpc = os.getenv("POLYGON_AMOY_RPC_URL") or os.getenv("RPC_URL") or os.getenv("ORACLE_RPC_URL")
        if not rpc:
            raise ValueError("Missing RPC URL (POLYGON_AMOY_RPC_URL / RPC_URL / ORACLE_RPC_URL)")
        contract = OracleConfig._addr("INDEX_ORACLE_CONSUMER_ADDRESS")
        key = os.getenv("ORACLE_SIGNER_PRIVATE_KEY") or os.getenv("DEPLOYER_PRIVATE_KEY")
        if not key:
            raise ValueError("Missing ORACLE_SIGNER_PRIVATE_KEY (or DEPLOYER_PRIVATE_KEY)")
        if not key.startswith("0x"):
            key = "0x" + key
        signer = Account.from_key(key)

        chain_id = int(os.getenv("CHAIN_ID", os.getenv("CHAIN_ID", "80002")))
        price_scale = int(os.getenv("INDEX_PRICE_SCALE", "100"))
        max_staleness = int(os.getenv("ORACLE_MAX_PRICE_STALENESS_SECONDS", "60"))
        interval = int(os.getenv("ORACLE_PUSH_INTERVAL_SECONDS", "15"))
        retries = int(os.getenv("ORACLE_RETRY_MAX_ATTEMPTS", "5"))
        backoff = int(os.getenv("ORACLE_RETRY_BACKOFF_SECONDS", "2"))

        templates = os.getenv("ACTIVE_BASKETS", "TOP20-{MONTH}").split(",")
        baskets = active_basket_names(templates)

        return OracleConfig(
            rpc_url=rpc,
            contract_address=contract,
            signer_private_key=key,
            signer_address=signer.address,
            chain_id=chain_id,
            price_scale=price_scale,
            max_staleness=max_staleness,
            push_interval_seconds=interval,
            retry_max_attempts=retries,
            retry_backoff_seconds=backoff,
            baskets=baskets,
            database_url=os.getenv("DATABASE_URL"),
            redis_url=os.getenv("REDIS_URL"),
        )