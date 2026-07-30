import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from xleuth_api.db import Database

logger = logging.getLogger("xleuth_api.routes.websocket")

router = APIRouter()

POLL_INTERVAL = 5.0


@router.websocket("/ws/price/{basket_name}")
async def websocket_price_stream(websocket: WebSocket, basket_name: str) -> None:
    await websocket.accept()
    redis = getattr(websocket.app.state, "redis", None)

    db: Database = websocket.app.state.db

    logger.info("WebSocket connected for basket %s", basket_name)

    send_queue: asyncio.Queue[str | None] = asyncio.Queue()

    try:
        if redis is None:
            logger.info("Redis not available; using DB polling fallback for basket %s", basket_name)

            async def poll_db():
                last_ts = None
                while True:
                    row = await db.get_latest_basket_price(basket_name)
                    if row and (last_ts is None or row["ts"] != last_ts):
                        last_ts = row["ts"]
                        payload = json.dumps(
                            {
                                "type": "price_update",
                                "basket_name": row["basket_name"],
                                "index_price": row.get("index_price"),
                                "scaled_price": row.get("scaled_price"),
                                "computed_at": row["ts"].isoformat() if hasattr(row["ts"], "isoformat") else str(row["ts"]),
                                "constituent_count": row.get("constituent_count"),
                            },
                            default=str,
                        )
                        await send_queue.put(payload)
                    await asyncio.sleep(POLL_INTERVAL)

            poll_task = asyncio.create_task(poll_db())
        else:
            channel = f"xleuth:basket:{basket_name}:price"
            pubsub = redis.pubsub()
            await pubsub.subscribe(channel)

            async def listen_redis():
                while True:
                    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if msg and msg["type"] == "message":
                        await send_queue.put(msg["data"])

            poll_task = asyncio.create_task(listen_redis())

        async def listen_client():
            while True:
                data = await websocket.receive_text()
                try:
                    msg = json.loads(data)
                    if msg.get("action") == "ping":
                        await websocket.send_json({"type": "pong"})
                    elif msg.get("action") == "subscribe" and msg.get("basket_name"):
                        await websocket.send_json({"type": "subscribed", "basket_name": msg["basket_name"]})
                except (json.JSONDecodeError, KeyError):
                    await websocket.send_json({"type": "error", "message": "Invalid message format"})

        async def listen_queue():
            while True:
                msg = await send_queue.get()
                if msg is None:
                    break
                await websocket.send_text(msg)

        client_task = asyncio.create_task(listen_client())
        queue_task = asyncio.create_task(listen_queue())

        done, pending = await asyncio.wait(
            [poll_task, client_task, queue_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for basket %s", basket_name)
    except Exception:
        logger.exception("WebSocket error for basket %s", basket_name)
