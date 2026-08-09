"""Encrypted, expiring cross-worker credential handoff."""

from __future__ import annotations

import base64
import hashlib
import time

import redis.asyncio as redis
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class APIKeyVault:
    TTL_SECONDS = settings.CREDENTIAL_TTL_SECONDS
    _redis = redis.from_url(settings.REDIS_URL, decode_responses=False)
    _local: dict[str, tuple[bytes, float]] = {}
    _fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(settings.JWT_SECRET_KEY.encode()).digest()))

    @classmethod
    async def stash(cls, submission_id: str, api_key: str) -> None:
        encrypted = cls._fernet.encrypt(api_key.encode())
        key = f"credential:submission:{submission_id}"
        try:
            await cls._redis.setex(key, cls.TTL_SECONDS, encrypted)
        except Exception:
            if settings.ENVIRONMENT.lower() == "production":
                raise RuntimeError("生产环境凭据保险库不可用")
            cls._local[submission_id] = (encrypted, time.monotonic() + cls.TTL_SECONDS)

    @classmethod
    async def retrieve_and_purge(cls, submission_id: str) -> str | None:
        key = f"credential:submission:{submission_id}"
        encrypted = None
        try:
            async with cls._redis.pipeline(transaction=True) as pipe:
                pipe.get(key); pipe.delete(key)
                encrypted, _ = await pipe.execute()
        except Exception:
            local = cls._local.pop(submission_id, None)
            if local and local[1] >= time.monotonic():
                encrypted = local[0]
        if not encrypted:
            return None
        try:
            return cls._fernet.decrypt(encrypted, ttl=cls.TTL_SECONDS).decode()
        except InvalidToken:
            return None

    @classmethod
    async def retrieve(cls, submission_id: str) -> str | None:
        """Read an evaluation-scoped credential without consuming it.

        Multi-Case evaluations purge the credential only after every Case has
        completed. Redis TTL remains the hard upper bound.
        """
        key = f"credential:submission:{submission_id}"
        encrypted = None
        try:
            encrypted = await cls._redis.get(key)
        except Exception:
            local = cls._local.get(submission_id)
            if local and local[1] >= time.monotonic():
                encrypted = local[0]
        if not encrypted:
            return None
        try:
            return cls._fernet.decrypt(encrypted, ttl=cls.TTL_SECONDS).decode()
        except InvalidToken:
            return None

    @classmethod
    async def purge(cls, submission_id: str) -> None:
        key = f"credential:submission:{submission_id}"
        cls._local.pop(submission_id, None)
        try:
            await cls._redis.delete(key)
        except Exception:
            pass
