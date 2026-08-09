from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


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
    build_mode: str
    build_status: str
    runtime_protocol: str
    image_digest: str | None = None
    matched_tools: list[ToolInfo] = Field(default_factory=list)
    risk_reasons: list[str] = Field(default_factory=list)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubmissionStatusResponse(BaseModel):
    id: str
    agent_name: str
    agent_type: str
    status: str
    risk_level: str
    status_message: str | None = None
    build_mode: str
    build_status: str
    runtime_protocol: str
    image_ref: str | None = None
    image_digest: str | None = None
    dockerfile_path: str | None = None
    build_log_path: str | None = None
    sbom_path: str | None = None
    image_scan_path: str | None = None
    config: dict | None = None
    matched_tools: list[ToolInfo] = Field(default_factory=list)
    risk_reasons: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
