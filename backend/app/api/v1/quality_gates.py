from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.core.security import get_current_user
from app.infrastructure.database import get_db
from app.infrastructure.quality_gate import QualityGateEngine
from app.models.evaluation import Evaluation
from app.models.quality_gate import QualityGate
from app.models.submission import Submission
from app.models.user import User
from app.services.websocket_service import publish_progress


router = APIRouter(prefix="/quality-gates", tags=["quality-gates"])
engine = QualityGateEngine()


class GateCheckRequest(BaseModel):
    evaluation_id: uuid.UUID
    gate_type: str
    metrics: dict[str, float]


async def _owned_submission(db: AsyncSession, submission_id: uuid.UUID, user: User) -> Submission:
    submission = await db.get(Submission, submission_id)
    if submission is None or (submission.user_id != user.id and user.role != "admin"):
        raise NotFoundException(f"Submission {submission_id} 不存在")
    return submission


@router.get("/{submission_id}")
async def list_quality_gates(
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _owned_submission(db, submission_id, current_user)
    query = (
        select(QualityGate)
        .join(Evaluation, QualityGate.evaluation_id == Evaluation.id)
        .where(Evaluation.submission_id == submission_id)
        .order_by(QualityGate.created_at.desc())
    )
    items = list((await db.execute(query)).scalars())
    return {
        "items": [
            {
                "id": str(item.id),
                "evaluation_id": str(item.evaluation_id),
                "gate_type": item.gate_type,
                "condition": item.condition,
                "threshold": item.threshold,
                "actual_value": item.actual_value,
                "passed": item.passed,
                "blocked": item.blocked,
                "created_at": item.created_at,
            }
            for item in items
        ],
        "passed": sum(item.passed for item in items),
        "blocked": sum(item.blocked for item in items),
    }


@router.post("/{submission_id}/check", status_code=201)
async def check_quality_gate(
    submission_id: uuid.UUID,
    request: GateCheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _owned_submission(db, submission_id, current_user)
    evaluation = await db.get(Evaluation, request.evaluation_id)
    if evaluation is None or evaluation.submission_id != submission_id:
        raise NotFoundException(f"Evaluation {request.evaluation_id} 不存在")
    result = engine.check_gate(request.gate_type, request.metrics)
    records = []
    for condition, check in result["checks"].items():
        record = QualityGate(
            evaluation_id=evaluation.id,
            gate_type=request.gate_type,
            condition=condition,
            threshold=str(check["required"]),
            actual_value=str(check["actual"]),
            passed=check["passed"],
            blocked=not check["passed"],
        )
        db.add(record)
        records.append(record)
    await db.flush()
    await publish_progress(str(submission_id), "quality_gate", result)
    return {**result, "record_ids": [str(record.id) for record in records]}
