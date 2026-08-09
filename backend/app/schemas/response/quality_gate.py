from datetime import datetime
from pydantic import BaseModel


class QualityGateResponse(BaseModel):
    id: str
    evaluation_id: str
    gate_type: str
    condition: str
    threshold: str
    actual_value: str
    passed: bool
    blocked: bool
    created_at: datetime

    class Config:
        from_attributes = True


class QualityGateListResponse(BaseModel):
    items: list[QualityGateResponse]
    passed: int
    blocked: int
