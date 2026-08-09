from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_db
from app.schemas.response.evaluation import EvaluationReport
from app.services.evaluation_service import evaluation_service
from app.core.security import get_current_user
from app.models.user import User
from app.models.evaluation import Evaluation
from app.models.submission import Submission


router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.post("/{submission_id}/start", status_code=202)
async def start_evaluation(
    submission_id: str,
    llm_api_key: str = Body(..., embed=True, min_length=1, max_length=8192),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    evaluation, task_id = await evaluation_service.start(
        db, submission_id, current_user.id, current_user.role == "admin", llm_api_key
    )
    return {"evaluation_id": str(evaluation.id), "task_id": task_id, "status": evaluation.status}


@router.get("/{evaluation_id}/result", response_model=EvaluationReport)
async def get_evaluation_result(evaluation_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    return await evaluation_service.get(db, evaluation_id, current_user.id, current_user.role == "admin")


@router.get("/{evaluation_id}/report", response_model=EvaluationReport)
async def get_evaluation_report(evaluation_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    return await evaluation_service.get(db, evaluation_id, current_user.id, current_user.role == "admin")


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
