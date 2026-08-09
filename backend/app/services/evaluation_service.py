from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.models.evaluation import Evaluation
from app.models.submission import Submission
from app.worker.tasks import build_evaluation_dag


class EvaluationService:
    async def start(self, db: AsyncSession, submission_id: str, user_id: uuid.UUID, is_admin: bool = False) -> tuple[Evaluation, str]:
        try:
            submission_uuid = uuid.UUID(submission_id)
        except ValueError as exc:
            raise ValidationException("submission_id 不是合法 UUID") from exc
        submission = await db.get(Submission, submission_uuid)
        if submission is None:
            raise NotFoundException(f"Submission {submission_id} 不存在")
        if submission.user_id != user_id and not is_admin:
            raise NotFoundException(f"Submission {submission_id} 不存在")
        if submission.status not in {"validated", "validated_with_warnings"}:
            raise ValidationException(f"Submission 状态不允许评测: {submission.status}")
        evaluation = Evaluation(
            submission_id=submission.id,
            status="queued",
            agent_type=submission.agent_type,
            horizon=submission.horizon,
        )
        db.add(evaluation)
        await db.flush()
        task = build_evaluation_dag(str(submission.id), str(evaluation.id), submission.horizon).apply_async()
        return evaluation, task.id

    async def get(self, db: AsyncSession, evaluation_id: str, user_id: uuid.UUID, is_admin: bool = False) -> Evaluation:
        try:
            value = uuid.UUID(evaluation_id)
        except ValueError as exc:
            raise ValidationException("evaluation_id 不是合法 UUID") from exc
        evaluation = await db.get(Evaluation, value)
        if evaluation is None:
            raise NotFoundException(f"Evaluation {evaluation_id} 不存在")
        submission = await db.get(Submission, evaluation.submission_id)
        if submission is None or (submission.user_id != user_id and not is_admin):
            raise NotFoundException(f"Evaluation {evaluation_id} 不存在")
        return evaluation


evaluation_service = EvaluationService()
