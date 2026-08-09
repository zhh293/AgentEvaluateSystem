from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class TestCaseResponse(BaseModel):
    id: UUID
    task_id: str
    agent_type: str
    horizon: str
    suite: str
    tier: str
    prompt: str
    context: dict | None = None
    expected_behavior: dict | None = None
    rubric: list[dict] = Field(default_factory=list)
    status: str
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TestCaseListResponse(BaseModel):
    items: list[TestCaseResponse]
    total: int
