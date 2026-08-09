import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.infrastructure.database import get_db
from app.models.audit import AuditLog


router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/audit-logs")
async def audit_logs(user_id: str | None = None, path: str | None = None, limit: int = Query(100, ge=1, le=500), db: AsyncSession = Depends(get_db)):
    query = select(AuditLog)
    if user_id: query = query.where(AuditLog.user_id == uuid.UUID(user_id))
    if path: query = query.where(AuditLog.path == path)
    items = list((await db.execute(query.order_by(AuditLog.created_at.desc()).limit(limit))).scalars())
    return [{"id": str(item.id), "user_id": str(item.user_id) if item.user_id else None, "method": item.method, "path": item.path, "status_code": item.status_code, "duration_ms": float(item.duration_ms), "ip": item.ip, "user_agent": item.user_agent, "created_at": item.created_at} for item in items]
