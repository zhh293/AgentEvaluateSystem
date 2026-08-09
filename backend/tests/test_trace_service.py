import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.trace_service import TraceService


@pytest.mark.asyncio
async def test_save_trace_persists_json_and_metadata():
    storage = MagicMock()
    db = MagicMock()
    db.flush = AsyncMock()
    service = TraceService(storage)
    evaluation_id = uuid.uuid4()
    trace = {
        "trace_id": "a" * 32,
        "spans": [
            {
                "span_id": "root",
                "parent_span_id": None,
                "duration_ms": 12.4,
                "status": "ok",
                "attributes": {"gen_ai.usage.total_tokens": 42},
            },
            {
                "span_id": "child",
                "parent_span_id": "root",
                "duration_ms": 3.2,
                "status": "error",
                "attributes": {},
            },
        ],
    }

    metadata = await service.save_trace(db, evaluation_id, trace)

    storage.upload_json.assert_called_once()
    db.add.assert_called_once_with(metadata)
    assert metadata.total_spans == 2
    assert metadata.total_tokens == 42
    assert metadata.error_spans == 1
    assert metadata.root_span_id == "root"


@pytest.mark.asyncio
async def test_save_trace_compensates_storage_on_database_failure():
    storage = MagicMock()
    db = MagicMock()
    db.flush = AsyncMock(side_effect=RuntimeError("db unavailable"))
    service = TraceService(storage)
    evaluation_id = uuid.uuid4()

    with pytest.raises(RuntimeError, match="db unavailable"):
        await service.save_trace(
            db, evaluation_id, {"trace_id": "trace", "spans": []}
        )

    storage.delete_package.assert_called_once()
