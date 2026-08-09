from datetime import datetime
from pydantic import BaseModel


class SubmissionResponse(BaseModel):
    id: str
    agent_name: str
    version: str
    agent_type: str
    horizon: str
    subtype: str | None = None
    risk_level: str
    status: str
    status_message: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class SubmissionStatusResponse(BaseModel):
    id: str
    status: str
    status_message: str | None = None
    updated_at: datetime

    class Config:
        from_attributes = True
