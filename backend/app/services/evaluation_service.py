from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, QueueUnavailableException, ValidationException
from app.models.case_set import CaseDefinition, CaseSet, EvaluationCase
from app.models.evaluation import Evaluation
from app.models.submission import Submission
from app.services.api_key_vault import APIKeyVault
from app.worker.tasks import build_evaluation_dag


class EvaluationService:
    async def start(
        self, db: AsyncSession, submission_id: str, user_id: uuid.UUID,
        is_admin: bool = False, llm_api_key: str = "", case_set_id: str | None = None,
    ) -> tuple[Evaluation, str]:
        try:
            submission_uuid = uuid.UUID(submission_id)
        except ValueError as exc:
            raise ValidationException("submission_id 不是合法 UUID") from exc
        submission = await db.get(Submission, submission_uuid)
        if submission is None or (submission.user_id != user_id and not is_admin):
            raise NotFoundException(f"Submission {submission_id} 不存在")
        if submission.status != "image_ready" or not submission.image_ref:
            raise ValidationException(f"Submission 状态不允许评估: {submission.status}")

        query = select(CaseSet).where(CaseSet.submission_id == submission.id, CaseSet.status == "ready")
        if case_set_id:
            try:
                query = query.where(CaseSet.id == uuid.UUID(case_set_id))
            except ValueError as exc:
                raise ValidationException("case_set_id 不是合法 UUID") from exc
        else:
            query = query.order_by(CaseSet.version.desc()).limit(1)
        case_set = (await db.execute(query)).scalar_one_or_none()
        if case_set is None:
            raise ValidationException("Submission 没有 ready 的 Case Set，必须先完成 Case Council")
        definitions = (await db.execute(
            select(CaseDefinition).where(CaseDefinition.case_set_id == case_set.id).order_by(CaseDefinition.case_key)
        )).scalars().all()
        if not definitions:
            raise ValidationException("ready Case Set 不包含任何 Case")

        evaluation = Evaluation(
            submission_id=submission.id, case_set_id=case_set.id, status="queued",
            agent_type=submission.agent_type, horizon=submission.horizon,
        )
        db.add(evaluation)
        await db.flush()
        snapshots: list[EvaluationCase] = []
        for definition in definitions:
            snapshot = EvaluationCase(
                evaluation_id=evaluation.id, case_set_id=case_set.id,
                case_key=definition.case_key, title=definition.title, suite=definition.suite,
                horizon=definition.horizon, capability_ids=definition.capability_ids,
                invocation=definition.invocation, rubrics=definition.rubrics, status="queued",
            )
            db.add(snapshot)
            snapshots.append(snapshot)
        await db.flush()
        await db.commit()
        credential_id = str(evaluation.id)
        try:
            await APIKeyVault.stash(credential_id, llm_api_key)
            task = build_evaluation_dag(
                str(submission.id), credential_id, submission.horizon,
                [str(snapshot.id) for snapshot in snapshots],
            ).apply_async()
        except Exception as exc:
            await APIKeyVault.purge(credential_id)
            evaluation.status = "failed"
            await db.commit()
            raise QueueUnavailableException("无法安全保存运行凭据或将评估任务加入队列") from exc
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
