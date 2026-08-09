import asyncio
import json
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.core.security import get_current_user
from app.infrastructure.database import get_db
from app.infrastructure.minio import minio_client
from app.models.trace import TraceMetadata
from app.models.user import User
from app.services.evaluation_service import evaluation_service


router = APIRouter(prefix="/evaluations", tags=["trace"])


async def _trace_for_evaluation(db, evaluation_id: str, current_user: User):
    try: value = uuid.UUID(evaluation_id)
    except ValueError as exc: raise ValidationException("evaluation_id 不是合法 UUID") from exc
    await evaluation_service.get(db, evaluation_id, current_user.id, current_user.role == "admin")
    metadata = (await db.execute(select(TraceMetadata).where(TraceMetadata.evaluation_id == value))).scalars().first()
    if metadata is None: raise NotFoundException("Trace 不存在")
    return minio_client.get_json(metadata.storage_path)


@router.get("/{evaluation_id}/trace")
async def get_trace(evaluation_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    return await _trace_for_evaluation(db, evaluation_id, current_user)


@router.get("/{evaluation_id}/trace/replay")
async def replay_trace(evaluation_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    trace = await _trace_for_evaluation(db, evaluation_id, current_user)
    async def events():
        for span in sorted(trace.get("spans", []), key=lambda item: item.get("started_ns", 0)):
            yield f"event: span\ndata: {json.dumps(span, ensure_ascii=False, default=str)}\n\n"
            await asyncio.sleep(0)
        yield "event: complete\ndata: {}\n\n"
    return StreamingResponse(events(), media_type="text/event-stream")
