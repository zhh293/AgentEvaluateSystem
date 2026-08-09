from datetime import datetime
from pydantic import BaseModel


class ToolInfo(BaseModel):
    id: str
    name: str
    category: str
    risk_level: str


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
    matched_tools: list[ToolInfo] = []
    risk_reasons: list[str] = []
    created_at: datetime

    class Config:
        from_attributes = True


class SubmissionStatusResponse(BaseModel):
    id: str
    agent_name: str
    agent_type: str
    status: str
    risk_level: str
    status_message: str | None = None
    config: dict | None = None
    matched_tools: list[ToolInfo] = []
    risk_reasons: list[str] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
