from datetime import datetime
from pydantic import BaseModel


class TestCaseResponse(BaseModel):
    id: str
    task_id: str
    agent_type: str
    horizon: str
    suite: str
    tier: str
    prompt: str
    context: dict | None = None
    expected_behavior: dict | None = None
    rubric: dict | None = None
    status: str
    version: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TestCaseListResponse(BaseModel):
    items: list[TestCaseResponse]
    total: int
