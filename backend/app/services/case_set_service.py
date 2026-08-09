from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundException, ValidationException
from app.engine.case_council import CaseCouncil, CouncilMember
from app.engine.case_set_validator import recommended_case_count, validate_case_set
from app.engine.llm_judge import HTTPJudgeTransport
from app.models.capability import Capability, CapabilityCatalog
from app.models.case_set import CaseDefinition, CaseSet
from app.models.submission import Submission
from app.services.lifecycle import CASE_SET_TRANSITIONS, CaseSetStatus, transition


class CaseSetService:
    async def generate(self, db: AsyncSession, submission_id: str, target_count: int | None = None) -> CaseSet:
        submission = await db.get(Submission, uuid.UUID(submission_id))
        if submission is None:
            raise NotFoundException("Submission 不存在")
        if submission.status != "image_ready":
            raise ValidationException("只有 image_ready 的 Submission 才能生成正式 Case Set")
        catalog = (await db.execute(
            select(CapabilityCatalog).where(CapabilityCatalog.submission_id == submission.id)
        )).scalar_one_or_none()
        if catalog is None or catalog.status != "ready":
            raise ValidationException("Capability Catalog 尚未 ready")
        capabilities = (await db.execute(
            select(Capability).where(Capability.catalog_id == catalog.id).order_by(Capability.capability_key)
        )).scalars().all()
        target = target_count or recommended_case_count(len(capabilities), submission.horizon)
        if not 30 <= target <= 60:
            raise ValidationException("target_count 必须在 30-60 之间")
        version = int((await db.execute(
            select(func.coalesce(func.max(CaseSet.version), 0)).where(CaseSet.submission_id == submission.id)
        )).scalar_one()) + 1
        case_set = CaseSet(
            submission_id=submission.id, capability_catalog_id=catalog.id,
            version=version, status="pending", target_case_count=target,
        )
        db.add(case_set)
        await db.flush()
        transition(case_set, CaseSetStatus.COUNCIL_REVIEWING, CASE_SET_TRANSITIONS)
        await db.commit()
        await db.refresh(case_set)
        capability_payload = [{
            "capability_key": item.capability_key, "kind": item.kind, "name": item.name,
            "description": item.description, "operation": item.operation,
            "input_schema": item.input_schema, "output_schema": item.output_schema,
        } for item in capabilities]
        models = [item.strip() for item in settings.CASE_COUNCIL_MODELS.split(",") if item.strip()]
        if len(models) < 3:
            raise ValidationException("CASE_COUNCIL_MODELS 至少需要配置 3 个成员")
        roles = ["functional", "boundary_recovery", "security", "long_horizon"]
        members = [CouncilMember(
            name=f"member-{index + 1}", model=model, role=roles[index % len(roles)],
            transport=HTTPJudgeTransport(model, settings.JUDGE_API_KEY, settings.JUDGE_API_BASE, timeout=settings.JUDGE_API_TIMEOUT, max_tokens=16_000),
        ) for index, model in enumerate(models)]
        chair_model = settings.CASE_COUNCIL_CHAIR_MODEL
        chairman = CouncilMember(
            name="chairman", model=chair_model, role="functional",
            transport=HTTPJudgeTransport(chair_model, settings.JUDGE_API_KEY, settings.JUDGE_API_BASE, timeout=settings.JUDGE_API_TIMEOUT, max_tokens=32_000),
        )
        try:
            output = await CaseCouncil(members, chairman, settings.CASE_COUNCIL_MIN_REVIEWERS).generate(
                capability_payload,
                {"name": submission.agent_name, "description": submission.config.get("description", ""), "horizon": submission.horizon, "subtype": submission.subtype},
                target,
            )
            capability_map = {item.capability_key: {"kind": item.kind, "operation": item.operation} for item in capabilities}
            report = validate_case_set(
                list(output.cases), capability_map, target,
                entry_service=str((submission.config.get("runtime_config") or {}).get("entry_service", submission.entry_service)),
            )
            case_set.council_provenance = output.provenance
            case_set.validation_report = {"errors": list(report.errors), "warnings": list(report.warnings)}
            case_set.coverage = report.coverage
            case_set.actual_case_count = len(output.cases)
            case_set.content_digest = report.content_digest
            transition(
                case_set, CaseSetStatus.READY if report.valid else CaseSetStatus.NEEDS_REVIEW,
                CASE_SET_TRANSITIONS,
            )
            for case in output.cases:
                db.add(CaseDefinition(
                    case_set_id=case_set.id, case_key=case.id, title=case.title,
                    suite=case.suite, horizon=case.horizon, capability_ids=case.capability_ids,
                    setup=case.setup, invocation=case.invocation.model_dump(mode="json"),
                    constraints=case.constraints,
                    rubrics=[item.model_dump(mode="json") for item in case.rubrics],
                    provenance={"source": "case_council", "case_set_digest": report.content_digest},
                ))
            await db.commit()
            await db.refresh(case_set)
            return case_set
        except Exception:
            if case_set.status == CaseSetStatus.COUNCIL_REVIEWING.value:
                transition(case_set, CaseSetStatus.VALIDATION_FAILED, CASE_SET_TRANSITIONS)
            await db.commit()
            raise


case_set_service = CaseSetService()
