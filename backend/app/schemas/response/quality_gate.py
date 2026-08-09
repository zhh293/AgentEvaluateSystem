from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class QualityGateResponse(BaseModel):
    id: UUID
    evaluation_id: UUID
    gate_type: str
    condition: str
    threshold: str
    actual_value: str
    passed: bool
    blocked: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class QualityGateListResponse(BaseModel):
    items: list[QualityGateResponse]
    passed: int
    blocked: int
