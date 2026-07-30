import logging
import os
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from xleuth_api.auth.jwt import JWTHandler
from xleuth_api.auth.siwe import SIWEHandler
from xleuth_api.db import Database
from xleuth_api.routes.accounts import router as accounts_router
from xleuth_api.routes.auth import router as auth_router
from xleuth_api.routes.baskets import router as baskets_router
from xleuth_api.routes.websocket import router as websocket_router

load_dotenv()

logger = logging.getLogger("xleuth_api")


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

    origins = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    database_url = os.getenv("DATABASE_URL")
    jwt_secret = os.getenv("JWT_SECRET", "changeme-generate-a-real-256bit-secret")
    jwt_expiry = int(os.getenv("JWT_EXPIRY_MINUTES", "60"))
    nonce_ttl = int(os.getenv("SIWE_NONCE_TTL_SECONDS", "300"))

    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    redis_db = int(os.getenv("REDIS_DB", "0"))

    db = Database(dsn=database_url)
    jwt_handler = JWTHandler(secret=jwt_secret, expiry_minutes=jwt_expiry)
    siwe_handler = SIWEHandler(nonce_ttl=nonce_ttl)

    app.state.db = db
    app.state.jwt_handler = jwt_handler
    app.state.siwe_handler = siwe_handler
    app.state.redis = None

    app.include_router(auth_router)
    app.include_router(baskets_router)
    app.include_router(accounts_router)
    app.include_router(websocket_router)

    return app


app = create_app()
