"""FastAPI service for the matching engine.

Endpoints:

  POST   /orders                     place a limit, market, or stop order (margin pre-checked)
  DELETE /orders/{order_id}          cancel a resting order
  GET    /orders/{order_id}          query an order's status / fills
  GET    /baskets/{basket_name}/book order book depth snapshot

Auth: bearer internal HS256 JWT issued by backend-api /auth/verify;
the wallet from the token's `sub` claim is the trader on the order
and must have a TRADER{1,2,...}_PRIVATE_KEY configured for on-chain settlement.

Place flow (Week-5 spec 2 and 3):

  1. margin pre-check against live on-chain state (oracle freshness,
     leverage cap, free balance) — rejected with a code-path `reason`
  2. price-time priority placement in the basket's book (limit)
     or FOK execution with slippage guard (market)
     or GTC stop order placement (stop)
  3. any fills are settled on-chain via SettlementBridge (trader-signed
     PositionManager.updatePosition); the fill is confirmed to the caller
     ONLY when the transaction is mined (receipt status 1)
  4. every accepted/cancelled order re-publishes the depth snapshot on
     Redis channel `xleuth:basket:{basket}:book` for the WS feed
  5. background task evaluates stop order triggers against mark/index price

The engine runs one instance (uvicorn on ENGINE_PORT), so placement/cancel
are naturally serialized.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
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
    OrderType,
    Side,
)
from xleuth_matching.settlement import SettlementBridge, SettlementOutcome
from xleuth_shared.auth.internal_jwt import InternalJWTConfig, InternalJWTVerifier, InternalJWTError
from xleuth_shared.schemas.orders import (
    OrderResponse,
    CancelResponse,
    BookSnapshot,
    RejectionCode,
    OrderListResponse,
    PositionsResponse,
)

logger = logging.getLogger("xleuth_matching.api")

BOOK_CHANNEL = "xleuth:basket:{basket}:book"

bearer = HTTPBearer(auto_error=False)


class OrderRequest(BaseModel):
    basket_name: str
    side: Side | None = Field(default=None)
    size: float | None = Field(default=None, gt=0)
    leverage: int | None = Field(default=None, ge=1)
    order_type: OrderType = OrderType.LIMIT
    price: float | None = Field(default=None, gt=0)  # Required for limit, not for market/stop/SL-TP
    max_slippage_bps: int = Field(default=0, ge=0, le=10000)  # For market/stop/SL-TP orders
    trigger_price: float | None = Field(default=None, gt=0)  # Required for stop/SL-TP orders
    position_id: str | None = Field(default=None)  # Required for SL/TP orders
    oco_group_id: str | None = Field(default=None)  # For OCO pairing


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
        # Internal JWT verifier (HS256 token issued by backend-api)
        self.internal_verifier = InternalJWTVerifier(
            InternalJWTConfig(secret=self.config.jwt_secret)
        )
        # Background task for stop order trigger evaluation
        self._trigger_task: asyncio.Task | None = None
        self._trigger_interval = int(os.getenv("STOP_TRIGGER_CHECK_INTERVAL_SECONDS", "5"))

    def book(self, basket_name: str) -> BasketOrderBook:
        return self.books.get(basket_name)

    async def start_trigger_evaluation(self) -> None:
        """Start the background task for stop order trigger evaluation."""
        if self._trigger_task is not None:
            return
        self._trigger_task = asyncio.create_task(self._trigger_evaluation_loop())
        logger.info("Started stop order trigger evaluation task")

    async def stop_trigger_evaluation(self) -> None:
        """Stop the background task for stop order trigger evaluation."""
        if self._trigger_task is not None:
            self._trigger_task.cancel()
            try:
                await self._trigger_task
            except asyncio.CancelledError:
                pass
            self._trigger_task = None
            logger.info("Stopped stop order trigger evaluation task")

    async def _trigger_evaluation_loop(self) -> None:
        """Periodically check stop order triggers against mark/index price."""
        while True:
            try:
                await asyncio.sleep(self._trigger_interval)
                await self._evaluate_all_triggers()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in trigger evaluation loop")

    async def _evaluate_all_triggers(self) -> None:
        """Evaluate stop order and SL/TP triggers for all baskets."""
        for basket_name in self.config.baskets:
            try:
                # Get current mark/index price from oracle
                oracle_result = self.chain.oracle_price(basket_name)
                if oracle_result is None:
                    continue
                price_int, _ = oracle_result
                if price_int <= 0:
                    continue
                # Oracle price is in 0-100 scale (price_scale=100)
                # Convert to float: price_int / 100.0 gives the 0-100 float value
                mark_price = price_int / 100.0
                
                book = self.books.get(basket_name)
                
                # Check stop order triggers
                triggered_results = book.check_triggers(mark_price)
                
                for result in triggered_results:
                    # Handle fills from triggered stop orders
                    fills = result.fills
                    if fills:
                        outcomes = self.bridge.settle_fills(fills)
                        confirmed, failed = _confirm_fills(self, fills, outcomes)
                        _publish_book(self, basket_name)
                        
                        # Log trigger execution
                        if confirmed:
                            logger.info(
                                "Stop order triggered and filled: basket=%s order_id=%s fills=%d",
                                basket_name, result.order.order_id, len(confirmed)
                            )
                        if failed:
                            logger.warning(
                                "Stop order triggered but settlement failed: basket=%s order_id=%s error=%s",
                                basket_name, result.order.order_id, failed[0].get("error")
                            )
                
                # Check SL/TP triggers
                sltp_results = book.check_sltp_triggers(mark_price)
                
                for result in sltp_results:
                    fills = result.fills
                    if fills:
                        outcomes = self.bridge.settle_fills(fills)
                        confirmed, failed = _confirm_fills(self, fills, outcomes)
                        _publish_book(self, basket_name)
                        
                        if confirmed:
                            logger.info(
                                "SL/TP order triggered and filled: basket=%s order_id=%s type=%s fills=%d",
                                basket_name, result.order.order_id, result.order.order_type.value, len(confirmed)
                            )
                        if failed:
                            logger.warning(
                                "SL/TP order triggered but settlement failed: basket=%s order_id=%s error=%s",
                                basket_name, result.order.order_id, failed[0].get("error")
                            )
            except Exception:
                logger.exception("Error evaluating triggers for basket %s", basket_name)


def get_engine(request: Request) -> Engine:
    return request.app.state.engine


def get_wallet(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    engine: Engine = Depends(get_engine),
) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="token_missing")
    try:
        wallet = engine.internal_verifier.verify_token(credentials.credentials)
    except InternalJWTError as e:
        raise HTTPException(status_code=401, detail=e.code)
    return wallet


def _get_position_from_chain(engine: Engine, wallet: str, basket_name: str, position_id: str) -> tuple[Side, float, int] | None:
    """Get position details from chain. Returns (side, size, leverage) or None if not found."""
    try:
        position = engine.chain.get_position(wallet, basket_name)
        if position is None:
            return None
        side_enum, size, leverage = position
        if size == 0:
            return None
        
        position_side = Side.BUY if side_enum == 0 else Side.SELL
        # For closing a position, the order side is opposite of position side
        close_side = position_side.opposite()
        
        return close_side, float(size), leverage
    except Exception as e:
        logger.warning("Failed to get position from chain: %s", e)
        return None


def create_app(config: MatchingConfig | None = None, chain=None, bridge: SettlementBridge | None = None) -> FastAPI:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        await app.state.engine.start_trigger_evaluation()
        yield
        # Shutdown
        await app.state.engine.stop_trigger_evaluation()

    app = FastAPI(title="Xleuth Matching Engine", version="0.1.0", lifespan=lifespan)
    
    # CORS middleware
    config_obj = config or MatchingConfig.load()
    if config_obj.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config_obj.cors_allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    engine = Engine(config, chain=chain, bridge=bridge)
    app.state.engine = engine

    @app.post("/orders", status_code=201, response_model=OrderResponse)
    def place_order(
        body: OrderRequest,
        wallet: str = Depends(get_wallet),
        engine: Engine = Depends(get_engine),
    ) -> dict[str, Any]:
        # Validate request based on order type
        if body.order_type == OrderType.LIMIT:
            if body.price is None:
                raise HTTPException(status_code=422, detail="price required for limit orders")
            if body.side is None:
                raise HTTPException(status_code=422, detail="side required for limit orders")
            if body.size is None:
                raise HTTPException(status_code=422, detail="size required for limit orders")
            if body.leverage is None:
                raise HTTPException(status_code=422, detail="leverage required for limit orders")
        elif body.order_type == OrderType.MARKET:
            if body.max_slippage_bps == 0:
                raise HTTPException(status_code=422, detail="max_slippage_bps required for market orders")
            if body.side is None:
                raise HTTPException(status_code=422, detail="side required for market orders")
            if body.size is None:
                raise HTTPException(status_code=422, detail="size required for market orders")
            if body.leverage is None:
                raise HTTPException(status_code=422, detail="leverage required for market orders")
        elif body.order_type == OrderType.STOP:
            if body.trigger_price is None:
                raise HTTPException(status_code=422, detail="trigger_price required for stop orders")
            if body.max_slippage_bps == 0:
                raise HTTPException(status_code=422, detail="max_slippage_bps required for stop orders")
            if body.side is None:
                raise HTTPException(status_code=422, detail="side required for stop orders")
            if body.size is None:
                raise HTTPException(status_code=422, detail="size required for stop orders")
            if body.leverage is None:
                raise HTTPException(status_code=422, detail="leverage required for stop orders")
        elif body.order_type in (OrderType.STOP_LOSS, OrderType.TAKE_PROFIT):
            if body.trigger_price is None:
                raise HTTPException(status_code=422, detail="trigger_price required for SL/TP orders")
            if body.max_slippage_bps == 0:
                raise HTTPException(status_code=422, detail="max_slippage_bps required for SL/TP orders")
            if body.position_id is None:
                raise HTTPException(status_code=422, detail="position_id required for SL/TP orders")
            
            # For SL/TP, derive side, size, leverage from position if not provided
            position_data = _get_position_from_chain(engine, wallet, body.basket_name, body.position_id)
            if position_data is None:
                raise HTTPException(status_code=422, detail="position_not_found")
            
            derived_side, derived_size, derived_leverage = position_data
            
            # If client provided values, validate they match derived values
            if body.side is not None and body.side != derived_side:
                raise HTTPException(status_code=422, detail="sl_tp_field_mismatch")
            if body.size is not None and abs(body.size - derived_size) > 1e-9:
                raise HTTPException(status_code=422, detail="sl_tp_field_mismatch")
            if body.leverage is not None and body.leverage != derived_leverage:
                raise HTTPException(status_code=422, detail="sl_tp_field_mismatch")
            
            # Use derived values
            body.side = derived_side
            body.size = derived_size
            body.leverage = derived_leverage
        else:
            raise HTTPException(status_code=422, detail=f"unsupported order type: {body.order_type}")

        # At this point, side, size, leverage are guaranteed to be set for all order types
        assert body.side is not None
        assert body.size is not None
        assert body.leverage is not None

        # Margin check: for market/stop orders, pass None for price to skip price validation
        # The validate method uses oracle price for margin calculation
        # For SL/TP, no additional margin check needed (position already has margin)
        if body.order_type in (OrderType.STOP_LOSS, OrderType.TAKE_PROFIT):
            # Skip margin check for SL/TP orders
            check = CheckResult(True, details={"oracle_price": 0, "required_usdc": 0.0})
        else:
            check = engine.margin.validate(
                basket_name=body.basket_name,
                wallet=wallet,
                side=body.side,
                price=body.price,  # None for market/stop orders, float for limit orders
                size=body.size,
                leverage=body.leverage,
            )
        if not check.ok:
            # For stop/SL-TP orders, return rejected order (like limit self-trade) instead of 422
            if body.order_type in (OrderType.STOP, OrderType.STOP_LOSS, OrderType.TAKE_PROFIT):
                order = OrderRecord(
                    order_id=uuid.uuid4().hex,
                    basket_name=body.basket_name,
                    trader=wallet,
                    side=body.side,
                    price=body.price if body.price is not None else 0.0,
                    size=body.size,
                    leverage=body.leverage,
                    order_type=body.order_type,
                    max_slippage_bps=body.max_slippage_bps,
                    trigger_price=body.trigger_price if body.trigger_price is not None else 0.0,
                    position_id=body.position_id or "",
                    oco_group_id=body.oco_group_id or "",
                )
                order.status = OrderStatus.REJECTED
                order.rejection_reason = check.message
                return _order_response(order, confirmed=[], failed=[], check=check)
            raise HTTPException(status_code=422, detail=check.message)

        order = OrderRecord(
            order_id=uuid.uuid4().hex,
            basket_name=body.basket_name,
            trader=wallet,
            side=body.side,
            price=body.price if body.price is not None else 0.0,
            size=body.size,
            leverage=body.leverage,
            order_type=body.order_type,
            max_slippage_bps=body.max_slippage_bps,
            trigger_price=body.trigger_price if body.trigger_price is not None else 0.0,
            position_id=body.position_id or "",
            oco_group_id=body.oco_group_id or "",
        )

        book = engine.book(body.basket_name)
        if body.order_type == OrderType.MARKET:
            placement = book.place_market(order)
        elif body.order_type == OrderType.STOP:
            placement = book.place_stop(order)
        elif body.order_type in (OrderType.STOP_LOSS, OrderType.TAKE_PROFIT):
            placement = book.place_sltp(order)
        else:
            placement = book.place(order)

        if placement.error is not None:
            # Return order with rejected status (like limit order self-trade)
            _publish_book(engine, body.basket_name)
            return _order_response(placement.order, confirmed=[], failed=[], check=check)

        fills = placement.fills
        outcomes = engine.bridge.settle_fills(fills) if fills else []
        confirmed, failed = _confirm_fills(engine, fills, outcomes)
        _publish_book(engine, body.basket_name)

        return _order_response(order, confirmed=confirmed, failed=failed, check=check)

    @app.delete("/orders/{order_id}", response_model=CancelResponse)
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
        return {
            "order_id": order.order_id,
            "status": order.status,
            "message": f"Order {order_id} cancelled"
        }

    @app.get("/orders/{order_id}", response_model=OrderResponse)
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

    @app.get("/baskets/{basket_name}/book", response_model=BookSnapshot)
    def book_depth(
        basket_name: str,
        engine: Engine = Depends(get_engine),
    ) -> dict[str, Any]:
        if basket_name not in engine.config.baskets:
            raise HTTPException(status_code=404, detail="unknown basket")
        snap = engine.book(basket_name).snapshot()
        # Convert to BookSnapshot format
        return {
            "basket_name": snap["basket_name"],
            "bids": [{"price": p, "size": s} for p, s in snap["bids"]],
            "asks": [{"price": p, "size": s} for p, s in snap["asks"]],
            "best_bid": snap["best_bid"],
            "best_ask": snap["best_ask"],
            "mid_price": snap["mid_price"],
            "spread": snap["spread"],
            "ts": snap["ts"],
        }

    @app.get("/orders", response_model=OrderListResponse)
    def list_orders(
        status: str | None = None,  # "open" | "history" | "all"
        basket_name: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
        wallet: str = Depends(get_wallet),
        engine: Engine = Depends(get_engine),
    ) -> dict[str, Any]:
        """List orders for the authenticated trader.
        
        Query params:
        - status: "open" (default) = open, partially_filled, plus resting stop/SL/TP
                  "history" = filled, cancelled, rejected, triggered
                  "all" = all orders
        - basket_name: optional filter by basket
        - limit: max results (default 50, max 200)
        - cursor: order_id for pagination (returns orders older than this)
        """
        if limit > 200:
            limit = 200
        if limit < 1:
            limit = 1
        
        # Determine status filter
        if status is None or status == "open":
            status_filter = "open"
        elif status == "history":
            status_filter = "history"
        elif status == "all":
            status_filter = "all"
        else:
            raise HTTPException(status_code=422, detail="status must be 'open', 'history', or 'all'")
        
        # Collect all orders for this trader
        all_orders: list[OrderRecord] = []
        for name in engine.books.names() or (engine.config.baskets or []):
            if basket_name and name != basket_name:
                continue
            book = engine.books.get(name)
            for order in book._orders.values():
                if order.trader.lower() != wallet:
                    continue
                all_orders.append(order)
            # Also check stop orders
            for order in book._stop_orders.values():
                if order.trader.lower() != wallet:
                    continue
                all_orders.append(order)
            # Also check SL/TP orders
            for order in book._sltp_orders.values():
                if order.trader.lower() != wallet:
                    continue
                all_orders.append(order)
        
        # Filter by status
        def matches_status(order: OrderRecord) -> bool:
            if status_filter == "open":
                return order.status in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)
            elif status_filter == "history":
                return order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.TRIGGERED)
            return True  # "all"
        
        filtered = [o for o in all_orders if matches_status(o)]
        
        # Sort by created_at descending (newest first)
        filtered.sort(key=lambda o: o.created_at, reverse=True)
        
        # Apply cursor pagination
        if cursor:
            cursor_idx = next((i for i, o in enumerate(filtered) if o.order_id == cursor), None)
            if cursor_idx is not None:
                filtered = filtered[cursor_idx + 1:]
        
        # Apply limit
        has_more = len(filtered) > limit
        page_orders = filtered[:limit]
        
        # Convert to response format
        next_cursor = page_orders[-1].order_id if has_more and page_orders else None
        
        items = []
        for order in page_orders:
            items.append({
                "order_id": order.order_id,
                "basket_name": order.basket_name,
                "side": order.side.value,
                "order_type": order.order_type,
                "price": order.price,
                "trigger_price": order.trigger_price if order.trigger_price > 0 else None,
                "size": order.size,
                "filled_size": order.filled_size,
                "remaining": order.remaining,
                "leverage": order.leverage,
                "status": order.status,
                "rejection_reason": order.rejection_reason,
                "created_at": order.created_at.isoformat(),
                "updated_at": order.created_at.isoformat(),  # No separate updated_at field
                "position_id": order.position_id if order.position_id else None,
                "oco_group_id": order.oco_group_id if order.oco_group_id else None,
                "average_fill_price": None,
            })
        
        return {
            "orders": items,
            "cursor": next_cursor,
            "has_more": has_more,
        }

    @app.get("/positions", response_model=PositionsResponse)
    def list_positions(
        wallet: str = Depends(get_wallet),
        engine: Engine = Depends(get_engine),
    ) -> dict[str, Any]:
        """List open positions for the authenticated trader."""
        positions: list[dict] = []
        
        # Get positions from on-chain for each basket
        for basket_name in engine.config.baskets:
            position = engine.chain.get_position(wallet, basket_name)
            if position is None:
                continue
            side_enum, size, leverage = position
            if size == 0:
                continue
            
            position_side = Side.BUY if side_enum == 0 else Side.SELL
            side_str = "long" if side_enum == 0 else "short"
            
            # Get mark price from oracle
            oracle_result = engine.chain.oracle_price(basket_name)
            if oracle_result is None:
                continue
            price_int, _ = oracle_result
            mark_price = price_int / 100.0
            
            # Get entry price from position
            # Need to call getPosition again for entry price
            try:
                from web3 import Web3
                from eth_utils import keccak
                
                w3 = Web3(Web3.HTTPProvider(engine.config.rpc_url, request_kwargs={"timeout": 15}))
                checksum_wallet = Web3.to_checksum_address(wallet)
                
                PM_ABI = [
                    {
                        "inputs": [
                            {"internalType": "address", "name": "user", "type": "address"},
                            {"internalType": "bytes32", "name": "basketId", "type": "bytes32"},
                        ],
                        "name": "getPosition",
                        "outputs": [
                            {"internalType": "enum PositionManager.Side", "name": "side", "type": "uint8"},
                            {"internalType": "uint256", "name": "size", "type": "uint256"},
                            {"internalType": "uint256", "name": "entryPrice", "type": "uint256"},
                            {"internalType": "uint256", "name": "leverage", "type": "uint256"},
                            {"internalType": "uint256", "name": "lockedMargin", "type": "uint256"},
                        ],
                        "stateMutability": "view",
                        "type": "function",
                    },
                ]
                
                basket_id = keccak(text=basket_name)
                pm = w3.eth.contract(address=engine.config.position_manager_address, abi=PM_ABI)
                result = pm.functions.getPosition(checksum_wallet, basket_id).call()
                
                entry_price = int(result[2]) / 100.0
                locked_margin = int(result[4]) / 1e6
            except Exception:
                entry_price = mark_price  # fallback
                locked_margin = (mark_price * size) / leverage  # fallback
            
            # Calculate unrealized PnL
            if position_side == Side.BUY:
                unrealized_pnl_abs = (mark_price - entry_price) * size
            else:
                unrealized_pnl_abs = (entry_price - mark_price) * size
            unrealized_pnl_pct = (unrealized_pnl_abs / (entry_price * size)) * 100 if entry_price * size > 0 else 0
            
            # Get SL/TP prices from resting orders
            sl_price = None
            tp_price = None
            sl_order_id = None
            tp_order_id = None
            oco_group_id = None
            
            for name in engine.books.names() or (engine.config.baskets or []):
                book = engine.books.get(name)
                for order in book._sltp_orders.values():
                    if order.trader.lower() == wallet and order.basket_name == basket_name:
                        if order.order_type == OrderType.STOP_LOSS:
                            sl_price = order.trigger_price
                            sl_order_id = order.order_id
                            oco_group_id = order.oco_group_id
                        elif order.order_type == OrderType.TAKE_PROFIT:
                            tp_price = order.trigger_price
                            tp_order_id = order.order_id
                            oco_group_id = order.oco_group_id
                # Also check triggered SL/TP orders in _orders
                for order in book._orders.values():
                    if order.trader.lower() == wallet and order.basket_name == basket_name:
                        if order.order_type == OrderType.STOP_LOSS and order.status in (OrderStatus.OPEN, OrderStatus.TRIGGERED):
                            sl_price = order.trigger_price
                            sl_order_id = order.order_id
                            oco_group_id = order.oco_group_id
                        elif order.order_type == OrderType.TAKE_PROFIT and order.status in (OrderStatus.OPEN, OrderStatus.TRIGGERED):
                            tp_price = order.trigger_price
                            tp_order_id = order.order_id
                            oco_group_id = order.oco_group_id
            
            # Use position_id format: wallet_basket_name (or similar)
            position_id = f"{wallet.lower()}_{basket_name}"
            
            positions.append({
                "position_id": position_id,
                "basket_name": basket_name,
                "side": side_str,
                "size": float(size),
                "leverage": leverage,
                "entry_price": entry_price,
                "mark_price": mark_price,
                "margin_usdc": locked_margin,
                "liquidation_price": None,  # Not derivable without maintenance margin param
                "unrealized_pnl_abs": unrealized_pnl_abs,
                "unrealized_pnl_pct": unrealized_pnl_pct,
                "stop_loss_price": sl_price,
                "take_profit_price": tp_price,
                "stop_loss_order_id": sl_order_id,
                "take_profit_order_id": tp_order_id,
                "oco_group_id": oco_group_id,
                "fee_paid": None,  # Not tracked
                "opened_at": datetime.now(timezone.utc).isoformat(),  # Not available on-chain
            })
        
        return {"positions": positions}

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
        "order_type": order.order_type.value,
        "price": order.price,
        "trigger_price": order.trigger_price if order.trigger_price > 0 else None,
        "size": order.size,
        "leverage": order.leverage,
        "status": order.status.value,
        "filled_size": order.filled_size,
        "remaining": order.remaining,
        "rejection_reason": order.rejection_reason,
        "created_at": order.created_at.isoformat(),
        "position_id": order.position_id if order.position_id else None,
        "oco_group_id": order.oco_group_id if order.oco_group_id else None,
        "average_fill_price": None,  # Not tracked yet
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