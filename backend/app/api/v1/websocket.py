import asyncio
import json
import uuid

import redis.asyncio as redis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.core.security import verify_token
from app.infrastructure.database import async_session_factory
from app.models.submission import Submission
from app.models.user import User
from app.services.websocket_service import ws_manager


router = APIRouter()


@router.websocket("/ws/{submission_id}")
async def evaluation_websocket(websocket: WebSocket, submission_id: str):
    token = websocket.query_params.get("token", "")
    try:
        payload = verify_token(token)
        user_id = uuid.UUID(payload["sub"])
        submission_uuid = uuid.UUID(submission_id)
        async with async_session_factory() as db:
            user = await db.get(User, user_id)
            submission = await db.get(Submission, submission_uuid)
            if user is None or submission is None or (submission.user_id != user.id and user.role != "admin"):
                raise PermissionError
    except Exception:
        await websocket.close(code=4401)
        return

    await ws_manager.connect(submission_id, websocket)
    client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(f"evaluation:{submission_id}")
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message.get("data"):
                await websocket.send_json(json.loads(message["data"]))
            try:
                incoming = await asyncio.wait_for(websocket.receive_text(), timeout=0.05)
                if incoming == "ping":
                    await websocket.send_json({"event": "pong", "data": {}})
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(f"evaluation:{submission_id}")
        await pubsub.aclose()
        await client.aclose()
        await ws_manager.disconnect(submission_id, websocket)
