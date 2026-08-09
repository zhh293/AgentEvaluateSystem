from __future__ import annotations

import uuid

from fastapi import APIRouter, Body, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, QueueUnavailableException, ValidationException
from app.core.security import get_current_user
from app.infrastructure.database import get_db
from app.models.capability import Capability, CapabilityCatalog
from app.models.case_set import CaseDefinition, CaseSet
from app.models.submission import Submission
from app.models.user import User
from app.worker.tasks import generate_submission_case_set


router = APIRouter(tags=["case-sets"])


async def _owned_submission(db: AsyncSession, submission_id: str, user: User) -> Submission:
    try:
        value = uuid.UUID(submission_id)
    except ValueError as exc:
        raise ValidationException("submission_id 不是合法 UUID") from exc
    submission = await db.get(Submission, value)
    if submission is None or (submission.user_id != user.id and user.role != "admin"):
        raise NotFoundException("Submission 不存在")
    return submission


@router.get("/submissions/{submission_id}/capabilities")
async def list_capabilities(submission_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    submission = await _owned_submission(db, submission_id, user)
    catalog = (await db.execute(select(CapabilityCatalog).where(CapabilityCatalog.submission_id == submission.id))).scalar_one_or_none()
    if catalog is None:
        raise NotFoundException("Capability Catalog 不存在")
    items = (await db.execute(select(Capability).where(Capability.catalog_id == catalog.id).order_by(Capability.capability_key))).scalars().all()
    return {
        "catalog_id": str(catalog.id), "status": catalog.status, "spec_type": catalog.spec_type,
        "spec_digest": catalog.spec_digest, "count": len(items),
        "items": [{
            "id": str(item.id), "capability_key": item.capability_key, "kind": item.kind,
            "name": item.name, "description": item.description, "operation": item.operation,
            "input_schema": item.input_schema, "output_schema": item.output_schema,
            "source_pointer": item.source_pointer, "verification_status": item.verification_status,
        } for item in items],
    }


@router.post("/submissions/{submission_id}/case-sets/generate", status_code=202)
async def generate_case_set(
    submission_id: str, target_count: int | None = Body(default=None, embed=True, ge=30, le=60),
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    submission = await _owned_submission(db, submission_id, user)
    if submission.status != "image_ready":
        raise ValidationException("只有 image_ready 的 Submission 才能生成 Case Set")
    try:
        task = generate_submission_case_set.delay(submission_id, target_count)
    except Exception as exc:
        raise QueueUnavailableException("无法将 Case Council 任务加入队列") from exc
    return {"submission_id": submission_id, "task_id": task.id, "status": "queued"}


@router.get("/submissions/{submission_id}/case-sets")
async def list_submission_case_sets(
    submission_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    submission = await _owned_submission(db, submission_id, user)
    items = (await db.execute(
        select(CaseSet).where(CaseSet.submission_id == submission.id).order_by(CaseSet.version.desc())
    )).scalars().all()
    return {"items": [{
        "id": str(item.id), "version": item.version, "status": item.status,
        "target_case_count": item.target_case_count, "actual_case_count": item.actual_case_count,
        "coverage": item.coverage, "validation_report": item.validation_report,
    } for item in items]}


@router.get("/case-sets/{case_set_id}")
async def get_case_set(case_set_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        value = uuid.UUID(case_set_id)
    except ValueError as exc:
        raise ValidationException("case_set_id 不是合法 UUID") from exc
    case_set = await db.get(CaseSet, value)
    if case_set is None:
        raise NotFoundException("Case Set 不存在")
    await _owned_submission(db, str(case_set.submission_id), user)
    cases = (await db.execute(select(CaseDefinition).where(CaseDefinition.case_set_id == case_set.id).order_by(CaseDefinition.case_key))).scalars().all()
    return {
        "id": str(case_set.id), "submission_id": str(case_set.submission_id), "version": case_set.version,
        "status": case_set.status, "target_case_count": case_set.target_case_count,
        "actual_case_count": case_set.actual_case_count, "coverage": case_set.coverage,
        "validation_report": case_set.validation_report, "content_digest": case_set.content_digest,
        "cases": [{
            "id": item.case_key, "title": item.title, "suite": item.suite,
            "horizon": item.horizon, "capability_ids": item.capability_ids,
            "invocation": item.invocation, "rubrics": item.rubrics,
        } for item in cases],
    }
