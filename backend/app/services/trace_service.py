"""Persist and retrieve normalized Agent traces."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.infrastructure.minio import MinIOClient, minio_client
from app.models.trace import TraceMetadata


class TraceService:
    def __init__(self, storage: MinIOClient = minio_client):
        self.storage = storage

    async def save_trace(
        self, db: AsyncSession, evaluation_id: str | uuid.UUID, trace_json: dict[str, Any]
    ) -> TraceMetadata:
        trace_id = str(trace_json.get("trace_id", "")).strip()
        spans = trace_json.get("spans")
        if not trace_id or not isinstance(spans, list):
            raise ValidationException("Trace 必须包含 trace_id 和 spans 列表")

        object_path = f"traces/{evaluation_id}/{trace_id}.json"
        self.storage.upload_json(object_path, trace_json)
        root = next((span for span in spans if not span.get("parent_span_id")), None) or {}
        duration_ms = sum(float(span.get("duration_ms", 0) or 0) for span in spans)
        metadata = TraceMetadata(
            evaluation_id=uuid.UUID(str(evaluation_id)),
            trace_id=trace_id,
            root_span_id=str(root.get("span_id", "")),
            total_spans=len(spans),
            total_duration_ms=round(duration_ms),
            total_tokens=sum(int(span.get("attributes", {}).get("gen_ai.usage.total_tokens", 0) or 0) for span in spans),
            error_spans=sum(1 for span in spans if span.get("status") == "error"),
            storage_path=object_path,
            spans_json_path=object_path,
        )
        db.add(metadata)
        try:
            await db.flush()
        except Exception:
            self.storage.delete_package(object_path)
            raise
        return metadata

    async def get_trace(self, db: AsyncSession, trace_id: str) -> dict[str, Any]:
        result = await db.execute(select(TraceMetadata).where(TraceMetadata.trace_id == trace_id))
        metadata = result.scalar_one_or_none()
        if metadata is None:
            raise NotFoundException(f"Trace {trace_id} 不存在")
        return self.storage.get_json(metadata.storage_path)


trace_service = TraceService()
