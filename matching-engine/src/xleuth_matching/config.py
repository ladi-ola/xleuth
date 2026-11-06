"""Matching-engine configuration, read from environment variables (.env).

Required:
  POLYGON_AMOY_RPC_URL / RPC_URL
  COLLATERAL_VAULT_ADDRESS
  POSITION_MANAGER_ADDRESS
  INDEX_ORACLE_CONSUMER_ADDRESS
  JWT_SECRET                  (shared HS256 secret for internal token verification)
  TRADER_PRIVATE_KEY            (testnet trader EOA keys the engine signs
                                  on-chain position txs with; TRADER2_...,
                                  TRADER3_... etc. are also scanned)

Optional (defaults shown):
  MAX_LEVERAGE=5
  MIN_ORDER_SIZE=10               (minimum order notional in USDC)
  TICK_SIZE=0.01
  TRADING_FEE_BPS=10
  ORACLE_MAX_PRICE_STALENESS_SECONDS=60
  INDEX_PRICE_SCALE=100
  ACTIVE_BASKETS=TOP20-{MONTH}
  REDIS_URL=redis://localhost:6379/0
  ENGINE_HOST=0.0.0.0
  ENGINE_PORT=8001
  CORS_ALLOWED_ORIGINS=http://localhost:8080,http://localhost:3000
"""

import os
import re
from dataclasses import dataclass, field

from eth_account import Account

from xleuth_shared.basket_lifecycle import active_basket_names

_TRADER_KEY_RE = re.compile(r"^TRADER\d*_PRIVATE_KEY$")

# Guardrail hook (PLAN.md): fail fast if a retired basket-specific env var is
# still set. Nothing retired yet — ACTIVE_BASKETS stays as fallback until the
# migrated rows are verified.
RETIRED_BASKET_ENV_VARS: tuple[str, ...] = ()


def _check_no_retired_env() -> None:
    stale = [v for v in RETIRED_BASKET_ENV_VARS if os.getenv(v)]
    if stale:
        raise ValueError(
            f"Retired basket env var(s) still set: {', '.join(stale)}. "
            "Baskets now live in the DB — unset these variables.")


@dataclass(frozen=True)
class MatchingConfig:
    rpc_url: str
    vault_address: str
    position_manager_address: str
    oracle_consumer_address: str
    jwt_secret: str
    chain_id: int
    price_scale: int
    max_leverage: int
    min_order_size: float
    tick_size: float
    trading_fee_bps: int
    max_price_staleness_seconds: int
    baskets: list[str] = field(default_factory=list)
    redis_url: str | None = None
    trader_keys: dict[str, str] = field(default_factory=dict)  # wallet -> private key
    cors_allowed_origins: list[str] = field(default_factory=list)
    host: str = "0.0.0.0"
    port: int = 8001
    settlement_engine_address: str | None = None

    @staticmethod
    def _addr(key: str) -> str:
        value = os.getenv(key, "").strip()
        if not value:
            raise ValueError(f"Missing required env var {key}")
        if not value.startswith("0x"):
            value = "0x" + value
        return value

    @staticmethod
    def _trader_keys() -> dict[str, str]:
        keys: dict[str, str] = {}
        for env_name, value in os.environ.items():
            if _TRADER_KEY_RE.match(env_name) and value:
                key = value if value.startswith("0x") else "0x" + value
                try:
                    address = Account.from_key(key).address.lower()
                except Exception:
                    continue
                keys[address] = key
        return keys

    @staticmethod
    def load() -> "MatchingConfig":
        _check_no_retired_env()
        rpc = os.getenv("POLYGON_AMOY_RPC_URL") or os.getenv("RPC_URL")
        if not rpc:
            raise ValueError("Missing RPC URL (POLYGON_AMOY_RPC_URL / RPC_URL)")

        jwt_secret = os.getenv("JWT_SECRET", "changeme-generate-a-real-256bit-secret")

        chain_id = int(os.getenv("CHAIN_ID", "80002"))
        price_scale = int(os.getenv("INDEX_PRICE_SCALE", "100"))
        max_leverage = int(os.getenv("MAX_LEVERAGE", "5"))
        min_order_size = float(os.getenv("MIN_ORDER_SIZE", "10"))
        tick_size = float(os.getenv("TICK_SIZE", "0.01"))
        trading_fee_bps = int(os.getenv("TRADING_FEE_BPS", "10"))
        max_staleness = int(os.getenv("ORACLE_MAX_PRICE_STALENESS_SECONDS", "60"))

        templates = os.getenv("ACTIVE_BASKETS", "TOP20-{MONTH}").split(",")
        baskets = active_basket_names(templates)

        cors_origins = [
            o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:8080,http://localhost:3000").split(",")
            if o.strip()
        ]

        return MatchingConfig(
            rpc_url=rpc,
            vault_address=MatchingConfig._addr("COLLATERAL_VAULT_ADDRESS"),
            position_manager_address=MatchingConfig._addr("POSITION_MANAGER_ADDRESS"),
            oracle_consumer_address=MatchingConfig._addr("INDEX_ORACLE_CONSUMER_ADDRESS"),
            jwt_secret=jwt_secret,
            chain_id=chain_id,
            price_scale=price_scale,
            max_leverage=max_leverage,
            min_order_size=min_order_size,
            tick_size=tick_size,
            trading_fee_bps=trading_fee_bps,
            max_price_staleness_seconds=max_staleness,
            baskets=baskets,
            redis_url=os.getenv("REDIS_URL"),
            trader_keys=MatchingConfig._trader_keys(),
            cors_allowed_origins=cors_origins,
            host=os.getenv("ENGINE_HOST", "0.0.0.0"),
            port=int(os.getenv("ENGINE_PORT", "8001")),
            settlement_engine_address=(os.getenv("SETTLEMENT_ENGINE_ADDRESS", "").strip() or None),
        )
