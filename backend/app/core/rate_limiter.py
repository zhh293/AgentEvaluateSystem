from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, redis_client=None, max_requests: int = 60, window_seconds: int = 60):
        self.redis = redis_client
        self.max_requests, self.window_seconds = max_requests, window_seconds
        self.local: dict[str, deque[float]] = defaultdict(deque)
        self.lock = asyncio.Lock()

    async def is_rate_limited(self, key: str, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        if self.redis is not None:
            try:
                member = f"{now}:{uuid.uuid4().hex}"
                async with self.redis.pipeline(transaction=True) as pipe:
                    pipe.zremrangebyscore(key, 0, now - self.window_seconds)
                    pipe.zadd(key, {member: now})
                    pipe.zcard(key)
                    pipe.expire(key, self.window_seconds)
                    _, _, count, _ = await pipe.execute()
                return int(count) > self.max_requests
            except Exception:
                pass
        async with self.lock:
            window = self.local[key]
            while window and window[0] <= now - self.window_seconds:
                window.popleft()
            window.append(now)
            return len(window) > self.max_requests
