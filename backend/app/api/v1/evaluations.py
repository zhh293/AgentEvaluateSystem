from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_db
from app.schemas.response.evaluation import EvaluationReport
from app.services.evaluation_service import evaluation_service
from app.core.security import get_current_user
from app.models.user import User
from app.models.evaluation import Evaluation
from app.models.submission import Submission
from app.models.case_set import EvaluationCase, ExecutionAttempt
from app.models.artifact import Artifact
from app.infrastructure.minio import minio_client
from app.core.exceptions import NotFoundException, ValidationException
import uuid


router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.post("/{submission_id}/start", status_code=202)
async def start_evaluation(
    submission_id: str,
    llm_api_key: str = Body(..., embed=True, min_length=1, max_length=8192),
    case_set_id: str | None = Body(default=None, embed=True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    evaluation, task_id = await evaluation_service.start(
        db, submission_id, current_user.id, current_user.role == "admin", llm_api_key, case_set_id
    )
    return {"evaluation_id": str(evaluation.id), "task_id": task_id, "status": evaluation.status}


@router.get("/{evaluation_id}/result", response_model=EvaluationReport)
async def get_evaluation_result(evaluation_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    return await evaluation_service.get(db, evaluation_id, current_user.id, current_user.role == "admin")


@router.get("/{evaluation_id}/report", response_model=EvaluationReport)
async def get_evaluation_report(evaluation_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    return await evaluation_service.get(db, evaluation_id, current_user.id, current_user.role == "admin")


@router.get("/{evaluation_id}/cases")
async def list_evaluation_cases(
    evaluation_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    evaluation = await evaluation_service.get(db, evaluation_id, current_user.id, current_user.role == "admin")
    items = (await db.execute(
        select(EvaluationCase).where(EvaluationCase.evaluation_id == evaluation.id).order_by(EvaluationCase.case_key)
    )).scalars().all()
    return {"items": [{
        "id": str(item.id), "case_key": item.case_key, "title": item.title,
        "suite": item.suite, "status": item.status, "capability_ids": item.capability_ids,
        "dimension_scores": item.dimension_scores, "unknown_weight": item.unknown_weight,
        "error_code": item.error_code,
    } for item in items]}


@router.get("/{evaluation_id}/cases/{case_id}")
async def get_evaluation_case(
    evaluation_id: str, case_id: str,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    evaluation = await evaluation_service.get(db, evaluation_id, current_user.id, current_user.role == "admin")
    try:
        value = uuid.UUID(case_id)
    except ValueError as exc:
        raise ValidationException("case_id 不是合法 UUID") from exc
    item = await db.get(EvaluationCase, value)
    if item is None or item.evaluation_id != evaluation.id:
        raise NotFoundException("Evaluation Case 不存在")
    attempts = (await db.execute(
        select(ExecutionAttempt).where(ExecutionAttempt.evaluation_case_id == item.id).order_by(ExecutionAttempt.attempt_number)
    )).scalars().all()
    return {
        "id": str(item.id), "case_key": item.case_key, "title": item.title,
        "suite": item.suite, "status": item.status, "capability_ids": item.capability_ids,
        "invocation": item.invocation, "rubrics": item.rubrics,
        "result": item.result, "dimension_scores": item.dimension_scores,
        "trace_artifact_id": str(item.trace_artifact_id) if item.trace_artifact_id else None,
        "unknown_weight": item.unknown_weight, "error_code": item.error_code,
        "error_message": item.error_message, "started_at": item.started_at,
        "completed_at": item.completed_at,
        "attempts": [{
            "id": str(attempt.id), "attempt_number": attempt.attempt_number,
            "status": attempt.status, "trace_artifact_id": str(attempt.trace_artifact_id) if attempt.trace_artifact_id else None,
            "error_code": attempt.error_code, "error_message": attempt.error_message,
            "started_at": attempt.started_at, "completed_at": attempt.completed_at,
        } for attempt in attempts],
    }


@router.get("/{evaluation_id}/cases/{case_id}/trace", response_class=JSONResponse)
async def get_evaluation_case_trace(
    evaluation_id: str, case_id: str,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    evaluation = await evaluation_service.get(db, evaluation_id, current_user.id, current_user.role == "admin")
    try:
        value = uuid.UUID(case_id)
    except ValueError as exc:
        raise ValidationException("case_id 不是合法 UUID") from exc
    item = await db.get(EvaluationCase, value)
    if item is None or item.evaluation_id != evaluation.id or item.trace_artifact_id is None:
        raise NotFoundException("Case Trace 不存在")
    artifact = await db.get(Artifact, item.trace_artifact_id)
    if artifact is None or artifact.owner_id != item.id or artifact.artifact_type != "raw_trace":
        raise NotFoundException("Case Trace Artifact 不存在")
    return JSONResponse(minio_client.get_json(artifact.storage_path))


@router.get("")
async def list_evaluations(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        select(Evaluation, Submission.agent_name)
        .join(Submission, Evaluation.submission_id == Submission.id)
        .order_by(Evaluation.created_at.desc())
        .limit(limit)
    )
    if current_user.role != "admin":
        query = query.where(Submission.user_id == current_user.id)
    rows = (await db.execute(query)).all()
    return {
        "items": [
            {
                "id": str(evaluation.id),
                "submission_id": str(evaluation.submission_id),
                "agent_name": agent_name,
                "status": evaluation.status,
                "agent_type": evaluation.agent_type,
                "overall_score": float(evaluation.overall_score) if evaluation.overall_score is not None else None,
                "grade": evaluation.grade,
                "created_at": evaluation.created_at,
            }
            for evaluation, agent_name in rows
        ]
    }
