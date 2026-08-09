from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.models.test_case import TestCase
from app.models.evaluation import Evaluation
from app.models.submission import Submission


class CaseManager:
    async def create_case(self, db: AsyncSession, case_data: dict) -> TestCase:
        existing = (await db.execute(select(TestCase).where(TestCase.task_id == case_data["task_id"]))).scalar_one_or_none()
        if existing:
            raise ValidationException(f"task_id 已存在: {case_data['task_id']}")
        case = TestCase(**case_data, status="draft")
        db.add(case); await db.flush(); await db.refresh(case)
        return case

    async def _get(self, db: AsyncSession, case_id: str) -> TestCase:
        try: value = uuid.UUID(case_id)
        except ValueError as exc: raise ValidationException("case_id 不是合法 UUID") from exc
        case = await db.get(TestCase, value)
        if case is None: raise NotFoundException(f"Case {case_id} 不存在")
        return case

    async def publish_case(self, db: AsyncSession, case_id: str) -> TestCase:
        case = await self._get(db, case_id)
        if case.status != "draft": raise ValidationException("只有 draft Case 可以发布")
        case.status = "published"; case.version += 1; await db.flush(); return case

    async def archive_case(self, db: AsyncSession, case_id: str) -> TestCase:
        case = await self._get(db, case_id)
        if case.status == "archived": return case
        case.status = "archived"; await db.flush(); return case

    async def list_cases(self, db: AsyncSession, *, agent_type: str | None = None, suite: str | None = None, tier: str | None = None, status: str | None = None, offset: int = 0, limit: int = 100):
        filters = []
        for column, value in ((TestCase.agent_type, agent_type), (TestCase.suite, suite), (TestCase.tier, tier), (TestCase.status, status)):
            if value: filters.append(column == value)
        query = select(TestCase).where(*filters).order_by(TestCase.created_at.desc()).offset(offset).limit(limit)
        count = select(func.count()).select_from(TestCase).where(*filters)
        return list((await db.execute(query)).scalars()), int((await db.execute(count)).scalar_one())

    async def convert_bad_case(self, db: AsyncSession, evaluation_id: str, failed_rubric_ids: list[str]) -> TestCase:
        try:
            value = uuid.UUID(evaluation_id)
        except ValueError as exc:
            raise ValidationException("evaluation_id 不是合法 UUID") from exc
        evaluation = await db.get(Evaluation, value)
        if evaluation is None:
            raise NotFoundException(f"Evaluation {evaluation_id} 不存在")
        submission = await db.get(Submission, evaluation.submission_id)
        if submission is None:
            raise NotFoundException("Evaluation 对应的 Submission 不存在")
        config = submission.config or {}
        case = TestCase(
            task_id=f"BAD-{str(evaluation.id)[:8]}-{uuid.uuid4().hex[:6]}",
            agent_type=evaluation.agent_type,
            horizon=evaluation.horizon,
            suite="regression",
            tier="regression",
            prompt=str(config.get("evaluation_input") or config.get("description") or submission.agent_name),
            context={"evaluation_id": str(evaluation.id), "report": evaluation.report_full or {}},
            expected_behavior={"failed_rubric_ids": failed_rubric_ids, "require_all_pass": True},
            rubric=[{"id": rubric_id} for rubric_id in failed_rubric_ids],
            source="bad_case_conversion",
            source_case_id=str(evaluation.id),
            status="draft",
        )
        db.add(case)
        await db.flush()
        await db.refresh(case)
        return case

    async def get_suite(self, db: AsyncSession, tier: str, agent_type: str | None = None) -> list[TestCase]:
        query = select(TestCase).where(TestCase.tier == tier, TestCase.status == "published")
        if agent_type:
            query = query.where(TestCase.agent_type == agent_type)
        return list((await db.execute(query.order_by(TestCase.created_at))).scalars())

    async def get_core_suite(self, db: AsyncSession, agent_type: str) -> list[TestCase]:
        return await self.get_suite(db, "core", agent_type)

    async def get_extended_suite(self, db: AsyncSession, agent_type: str) -> list[TestCase]:
        return await self.get_suite(db, "extended", agent_type)

    async def get_adversarial_suite(self, db: AsyncSession) -> list[TestCase]:
        return await self.get_suite(db, "adversarial")

    async def get_regression_suite(self, db: AsyncSession, agent_type: str) -> list[TestCase]:
        return await self.get_suite(db, "regression", agent_type)


case_manager = CaseManager()
