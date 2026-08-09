"""Structured and durable request auditing."""

from __future__ import annotations

import logging

from fastapi import Request

from app.infrastructure.database import async_session_factory
from app.models.audit import AuditLog


logger = logging.getLogger("audit")


async def record_audit(request: Request, status_code: int, duration_ms: float, user_id: str | None) -> None:
    fields = {
        "audit": True,
        "user_id": user_id,
        "method": request.method,
        "path": request.url.path,
        "status_code": status_code,
        "duration_ms": round(duration_ms, 3),
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent", "")[:500],
    }
    logger.info("api_request", extra=fields)
    try:
        async with async_session_factory() as session:
            session.add(AuditLog(**{key: value for key, value in fields.items() if key != "audit"}))
            await session.commit()
    except Exception:
        logger.warning("audit_persistence_failed", exc_info=True)
