import logging
import os
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from xleuth_api.auth.dynamic_jwt import DynamicAuthHandler
from xleuth_api.chain import ChainConfig, Web3ChainStateReader
from xleuth_api.db import Database
from xleuth_api.routes.accounts import router as accounts_router
from xleuth_api.routes.auth import router as auth_router
from xleuth_api.routes.baskets import router as baskets_router
from xleuth_api.routes.faucet import router as faucet_router
from xleuth_api.routes.websocket import router as websocket_router

load_dotenv()

logger = logging.getLogger("xleuth_api")


class CatchAllErrorMiddleware:
    """Convert uncaught exceptions into a JSON 500 that keeps CORS headers.

    Starlette registers a generic ``Exception`` handler on ServerErrorMiddleware,
    which is the *outermost* middleware — outside CORSMiddleware. Its 500
    responses therefore carry no ``Access-Control-*`` headers, so browsers
    report a misleading CORS error instead of the real failure. Running this
    middleware just inside CORSMiddleware means the JSON 500 flows back out
    through CORS and is labelled correctly.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def _send(message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except Exception:  # noqa: BLE001 - deliberate catch-all guard
            logger.exception(
                "Unhandled error on %s %s", scope.get("method"), scope.get("path")
            )
            if response_started:
                # Response already streaming; cannot replace it.
                raise
            response = JSONResponse({"detail": "Internal Server Error"}, status_code=500)
            await response(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_ok = await app.state.db.connect()
    if db_ok:
        await app.state.db.ensure_schema()
        logger.info("Database connected and schema ensured")
    else:
        logger.warning("Running without database persistence")
    try:
        app.state.redis = aioredis.from_url(
            f"redis://{redis_host}:{redis_port}/{redis_db}",
            decode_responses=True,
        )
        await app.state.redis.ping()
        logger.info("Redis connected")
    except Exception:
        logger.warning("Redis unavailable; WebSocket will be degraded")
        app.state.redis = None
    yield
    await app.state.db.close()
    if app.state.redis:
        await app.state.redis.aclose()


def create_app() -> FastAPI:
    global redis_host, redis_port, redis_db

    app = FastAPI(
        title="Xleuth API",
        version="0.1.0",
        description="Backend API for Xleuth index futures",
        lifespan=lifespan,
    )

    # Keep the configured origins, but always allow the production frontends
    # regardless of the deployed CORS_ALLOWED_ORIGINS value. No wildcards:
    # allow_credentials=True requires an explicit origin list.
    origins = [
        o.strip()
        for o in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
        if o.strip()
    ]
    for required_origin in ("https://xleuth.xyz", "https://www.xleuth.xyz"):
        if required_origin not in origins:
            origins.append(required_origin)

    # Task 16: per-IP rate limits on public endpoints + request size guard.
    # Rules are env-tunable (RL_*_PER_MIN); the faucet keeps its own 24h
    # per-wallet cooldown in addition to this IP limit.
    from xleuth_shared.rate_limit import RateLimitMiddleware

    # Middleware is added innermost-first: the last one added is the outermost.
    # CORSMiddleware must be outermost among these so that both the rate-limit
    # and catch-all responses (including 500s) carry CORS headers.
    app.add_middleware(RateLimitMiddleware, service="backend-api")
    app.add_middleware(CatchAllErrorMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    database_url = os.getenv("DATABASE_URL")
    dynamic_env_id = os.getenv("DYNAMIC_ENVIRONMENT_ID", "938a93a5-ee1f-4da2-86cf-27326bd01885")
    internal_jwt_secret = os.getenv("JWT_SECRET", "changeme-generate-a-real-256bit-secret")
    internal_jwt_expiry = int(os.getenv("JWT_EXPIRY_MINUTES", "60"))
    jwks_cache_ttl = int(os.getenv("DYNAMIC_JWKS_CACHE_TTL", "3600"))

    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    redis_db = int(os.getenv("REDIS_DB", "0"))

    # The vault's collateral token is the asset the faucet dispenses and the
    # asset whose wallet balance counts toward the portfolio's available
    # balance before it is deposited into the vault. The legacy faucet token is
    # summed too so earlier claims stay visible.
    test_usdc_address = os.getenv("TEST_USDC_ADDRESS", "")
    legacy_usdc_address = os.getenv("MOCK_USDC_ADDRESS", "")

    # Chain config for on-chain reads
    chain_config = ChainConfig(
        rpc_url=os.getenv("POLYGON_AMOY_RPC_URL") or os.getenv("RPC_URL", ""),
        vault_address=os.getenv("COLLATERAL_VAULT_ADDRESS", ""),
        position_manager_address=os.getenv("POSITION_MANAGER_ADDRESS", ""),
        oracle_consumer_address=os.getenv("INDEX_ORACLE_CONSUMER_ADDRESS", ""),
        chain_id=int(os.getenv("CHAIN_ID", "80002")),
        collateral_token_address=test_usdc_address or legacy_usdc_address,
        legacy_token_address=legacy_usdc_address if test_usdc_address else "",
    )

    db = Database(dsn=database_url)
    dynamic_auth_handler = DynamicAuthHandler(
        environment_id=dynamic_env_id,
        internal_jwt_secret=internal_jwt_secret,
        internal_jwt_expiry_minutes=internal_jwt_expiry,
        jwks_cache_ttl=jwks_cache_ttl,
    )

    chain_reader = Web3ChainStateReader(chain_config) if chain_config.rpc_url else None

    app.state.db = db
    app.state.dynamic_auth_handler = dynamic_auth_handler
    app.state.chain_reader = chain_reader
    app.state.redis = None

    app.include_router(auth_router)
    app.include_router(baskets_router)
    app.include_router(accounts_router)
    app.include_router(faucet_router)
    app.include_router(websocket_router)

    return app


app = create_app()