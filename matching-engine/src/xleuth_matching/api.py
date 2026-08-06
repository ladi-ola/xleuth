"""FastAPI service for the matching engine.

Endpoints:

  POST   /orders                     place a limit order (margin pre-checked)
  DELETE /orders/{order_id}          cancel a resting order
  GET    /orders/{order_id}          query an order's status / fills
  GET    /baskets/{basket_name}/book order book depth snapshot

Auth: bearer JWT issued by the backend-api /auth/login (shared JWT_SECRET);
the wallet from the token's `sub` is the trader on the order and must have a
TRADER{1,2,...}_PRIVATE_KEY configured for on-chain settlement.

Place flow (Week-5 spec 2 and 3):

  1. margin pre-check against live on-chain state (oracle freshness,
     leverage cap, free balance) — rejected with a code-path `reason`
  2. price-time priority placement in the basket's book
  3. any fills are settled on-chain via SettlementBridge (trader-signed
     PositionManager.updatePosition); the fill is confirmed to the caller
     ONLY when the transaction is mined (receipt status 1)
  4. every accepted/cancelled order re-publishes the depth snapshot on
     Redis channel `xleuth:basket:{basket}:book` for the WS feed

The engine runs one instance (uvicorn on ENGINE_PORT), so placement/cancel
are naturally serialized.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import jwt as pyjwt
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from xleuth_matching.config import MatchingConfig
from xleuth_matching.margin_check import CheckResult, MarginCheck, Web3ChainState
from xleuth_matching.orderbook import (
    BasketOrderBook,
    Fill,
    OrderBookManager,
    OrderRecord,
    OrderStatus,
    Side,
)
from xleuth_matching.settlement import SettlementBridge, SettlementOutcome

logger = logging.getLogger("xleuth_matching.api")

BOOK_CHANNEL = "xleuth:basket:{basket}:book"

bearer = HTTPBearer(auto_error=False)


class OrderRequest(BaseModel):
    basket_name: str
    side: Side
    price: float = Field(gt=0)
    size: float = Field(gt=0)
    leverage: int = Field(ge=1)


class Engine:
    """Wires config, chain state, books, and settlement into one app state."""

    def __init__(
        self,
        config: MatchingConfig | None = None,
        chain=None,
        bridge: SettlementBridge | None = None,
    ):
        self.config = config or MatchingConfig.load()
        self.chain = chain or Web3ChainState(self.config)
        self.margin = MarginCheck(self.config, self.chain)
        self.books = OrderBookManager(self.config.baskets)
        self.bridge = bridge or SettlementBridge(self.config)
        self._redis = self.bridge.redis  # shared optional redis client

    def book(self, basket_name: str) -> BasketOrderBook:
        return self.books.get(basket_name)


def get_engine(request: Request) -> Engine:
    return request.app.state.engine


def get_wallet(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    engine: Engine = Depends(get_engine),
) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        payload = pyjwt.decode(
            credentials.credentials, engine.config.jwt_secret, algorithms=["HS256"]
        )
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    wallet = (payload.get("sub") or "").lower()
    if not wallet:
        raise HTTPException(status_code=401, detail="token has no wallet subject")
    return wallet


def create_app(config: MatchingConfig | None = None, chain=None, bridge: SettlementBridge | None = None) -> FastAPI:
    app = FastAPI(title="Xleuth Matching Engine", version="0.1.0")
    engine = Engine(config, chain=chain, bridge=bridge)
    app.state.engine = engine

    @app.post("/orders", status_code=201)
    def place_order(
        body: OrderRequest,
        wallet: str = Depends(get_wallet),
        engine: Engine = Depends(get_engine),
    ) -> dict[str, Any]:
        check = engine.margin.validate(
            basket_name=body.basket_name,
            wallet=wallet,
            side=body.side,
            price=body.price,
            size=body.size,
            leverage=body.leverage,
        )
        if not check.ok:
            raise HTTPException(status_code=422, detail=check.message)

        order = OrderRecord(
            order_id=uuid.uuid4().hex,
            basket_name=body.basket_name,
            trader=wallet,
            side=body.side,
            price=body.price,
            size=body.size,
            leverage=body.leverage,
        )
        placement = engine.book(body.basket_name).place(order)
        if placement.error is not None:
            raise HTTPException(status_code=422, detail=f"rejected: {placement.error}")

        fills = placement.fills
        outcomes = engine.bridge.settle_fills(fills) if fills else []
        confirmed, failed = _confirm_fills(engine, fills, outcomes)
        _publish_book(engine, body.basket_name)

        return _order_response(order, confirmed=confirmed, failed=failed, check=check)

    @app.delete("/orders/{order_id}")
    def cancel_order(
        order_id: str,
        wallet: str = Depends(get_wallet),
        engine: Engine = Depends(get_engine),
    ) -> dict[str, Any]:
        order = None
        for name in engine.books.names() or (engine.config.baskets or []):
            order = engine.books.get(name).get_order(order_id)
            if order is not None:
                break
        if order is None:
            raise HTTPException(status_code=404, detail="order not found")
        if order.trader.lower() != wallet:
            raise HTTPException(status_code=403, detail="not your order")
        try:
            engine.books.get(order.basket_name).cancel(order_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        _publish_book(engine, order.basket_name)
        return _order_response(order)

    @app.get("/orders/{order_id}")
    def get_order(
        order_id: str,
        wallet: str = Depends(get_wallet),
        engine: Engine = Depends(get_engine),
    ) -> dict[str, Any]:
        order = None
        for name in engine.config.baskets or engine.books.names():
            order = engine.books.get(name).get_order(order_id)
            if order is not None:
                break
        if order is None:
            raise HTTPException(status_code=404, detail="order not found")
        if order.trader.lower() != wallet:
            raise HTTPException(status_code=403, detail="not your order")
        return _order_response(order)

    @app.get("/baskets/{basket_name}/book")
    def book_depth(
        basket_name: str,
        engine: Engine = Depends(get_engine),
    ) -> dict[str, Any]:
        if basket_name not in engine.config.baskets:
            raise HTTPException(status_code=404, detail="unknown basket")
        return engine.book(basket_name).snapshot()

    return app


# ── helpers ──────────────────────────────────────────────────────────────


def _confirm_fills(
    engine: Engine,
    fills: list[Fill],
    outcomes: list[SettlementOutcome],
) -> tuple[list[dict], list[dict]]:
    """Map settlement outcomes back onto fills.

    A fill is confirmed only if BOTH legs' on-chain updates mined (spec 3).
    Fills whose settlement failed leave their orders marked REJECTED with
    the settlement error so the failure is loud, not silently ignored.
    """
    by_wallet: dict[str, SettlementOutcome] = {}
    for outcome in outcomes:
        by_wallet.setdefault(outcome.update.wallet, outcome)

    confirmed: list[dict] = []
    failed: list[dict] = []
    for fill in fills:
        taker = by_wallet.get(fill.taker_trader.lower())
        maker = by_wallet.get(fill.maker_trader.lower())
        if taker is not None and not taker.ok or maker is not None and not maker.ok:
            error = (taker.error if taker and not taker.ok else None) or (
                maker.error if maker and not maker.ok else None
            )
            for order_id in (fill.taker_order_id, fill.maker_order_id):
                order = engine.books.get(fill.basket_name).get_order(order_id)
                if order is not None and order.status is not OrderStatus.CANCELLED:
                    order.status = OrderStatus.REJECTED
                    order.rejection_reason = f"settlement failed: {error}"
            failed.append(_fill_response(fill, confirmed=False, error=error))
            logger.error("FILL NOT CONFIRMED %s: %s", fill.trade_id, error)
        else:
            tx = (taker.tx_hash if taker and taker.ok else None) or (
                maker.tx_hash if maker and maker.ok else None
            )
            confirmed.append(_fill_response(fill, confirmed=True, tx_hash=tx))
            logger.info("FILL CONFIRMED %s price=%s size=%s tx=%s", fill.trade_id, fill.price, fill.size, tx)
    return confirmed, failed


def _fill_response(fill: Fill, confirmed: bool, tx_hash: str | None = None, error: str | None = None) -> dict:
    return {
        "trade_id": fill.trade_id,
        "basket_name": fill.basket_name,
        "price": fill.price,
        "size": fill.size,
        "taker_order_id": fill.taker_order_id,
        "maker_order_id": fill.maker_order_id,
        "taker_trader": fill.taker_trader,
        "maker_trader": fill.maker_trader,
        "taker_side": fill.taker_side.value,
        "maker_side": fill.maker_side.value,
        "notional": fill.notional,
        "confirmed": confirmed,
        "tx_hash": tx_hash,
        "error": error,
        "ts": fill.timestamp.isoformat(),
    }


def _order_response(
    order: OrderRecord,
    confirmed: list[dict] | None = None,
    failed: list[dict] | None = None,
    check: CheckResult | None = None,
) -> dict:
    resp = {
        "order_id": order.order_id,
        "basket_name": order.basket_name,
        "trader": order.trader,
        "side": order.side.value,
        "price": order.price,
        "size": order.size,
        "leverage": order.leverage,
        "status": order.status.value,
        "filled_size": order.filled_size,
        "remaining": order.remaining,
        "rejection_reason": order.rejection_reason,
        "created_at": order.created_at.isoformat(),
    }
    if confirmed is not None:
        resp["fills"] = confirmed
    if failed is not None:
        resp["failed_fills"] = failed
    if check is not None:
        resp["margin_check"] = {"ok": check.ok, "reason": check.reason, "details": check.details}
    return resp


def _publish_book(engine: Engine, basket_name: str) -> None:
    if engine._redis is None:
        return
    try:
        engine._redis.publish(BOOK_CHANNEL.format(basket=basket_name), json.dumps(engine.book(basket_name).snapshot()))
    except Exception:
        logger.warning("failed to publish book update for %s", basket_name, exc_info=True)


def _env_ready() -> bool:
    """True when the env vars needed to build the live engine are present."""
    return bool(
        os.getenv("COLLATERAL_VAULT_ADDRESS")
        and os.getenv("POSITION_MANAGER_ADDRESS")
        and os.getenv("INDEX_ORACLE_CONSUMER_ADDRESS")
        and (os.getenv("POLYGON_AMOY_RPC_URL") or os.getenv("RPC_URL"))
    )


app = create_app() if _env_ready() else None
