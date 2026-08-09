from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_admin
from app.infrastructure.case_manager import case_manager
from app.infrastructure.database import get_db
from app.schemas.request.test_case import CreateTestCaseRequest
from app.schemas.response.test_case import TestCaseListResponse, TestCaseResponse


router = APIRouter(prefix="/test-cases", tags=["test-cases"], dependencies=[Depends(get_current_user)])


class ConvertBadCaseRequest(BaseModel):
    evaluation_id: str
    failed_rubric_ids: list[str] = Field(min_length=1)


@router.get("", response_model=TestCaseListResponse)
async def list_cases(agent_type: str | None = None, suite: str | None = None, tier: str | None = None, status: str | None = None, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), db: AsyncSession = Depends(get_db)):
    items, total = await case_manager.list_cases(db, agent_type=agent_type, suite=suite, tier=tier, status=status, offset=offset, limit=limit)
    return TestCaseListResponse(items=items, total=total)


@router.post("", response_model=TestCaseResponse, status_code=201)
async def create_case(data: CreateTestCaseRequest, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    return await case_manager.create_case(db, data.model_dump())


@router.post("/convert", response_model=TestCaseResponse, status_code=201)
async def convert_bad_case(data: ConvertBadCaseRequest, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    return await case_manager.convert_bad_case(db, data.evaluation_id, data.failed_rubric_ids)


@router.put("/{case_id}/publish", response_model=TestCaseResponse)
async def publish_case(case_id: str, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    return await case_manager.publish_case(db, case_id)


@router.put("/{case_id}/archive", response_model=TestCaseResponse)
async def archive_case(case_id: str, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    return await case_manager.archive_case(db, case_id)
