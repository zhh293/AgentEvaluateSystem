from __future__ import annotations

import asyncio
import json
from collections import defaultdict

from fastapi import WebSocket
import redis.asyncio as redis

from app.core.config import settings


class WebSocketManager:
    def __init__(self):
        self.active_connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, submission_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.active_connections[submission_id].add(websocket)

    async def disconnect(self, submission_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self.active_connections.get(submission_id)
            if connections:
                connections.discard(websocket)
                if not connections:
                    self.active_connections.pop(submission_id, None)

    async def broadcast(self, submission_id: str, event: str, data: dict) -> None:
        payload = {"event": event, "data": data}
        dead = []
        for websocket in tuple(self.active_connections.get(submission_id, set())):
            try:
                await websocket.send_json(payload)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            await self.disconnect(submission_id, websocket)


ws_manager = WebSocketManager()


async def publish_progress(submission_id: str, event: str, data: dict) -> None:
    client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await client.publish(f"evaluation:{submission_id}", json.dumps({"event": event, "data": data}, default=str))
    except Exception:
        # Progress delivery is best-effort; durable state remains in PostgreSQL.
        return
    finally:
        await client.aclose()
