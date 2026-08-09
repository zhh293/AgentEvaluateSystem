from __future__ import annotations

import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


_ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]{0,127}$")
_DOMAIN = re.compile(
    r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)
_PLATFORM_ENV = {
    "AGENTEVAL_EVALUATION_ID", "AGENTEVAL_CASE_ID", "AGENTEVAL_ATTEMPT_ID",
    "LLM_API_BASE", "LLM_MODEL", "OTEL_EXPORTER_OTLP_ENDPOINT",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
}


class RuntimeProtocol(str, Enum):
    HTTP = "http"
    CLI = "cli"


class HealthcheckConfig(BaseModel):
    method: Literal["GET"] = "GET"
    path: str = "/health"

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value.startswith("/") or "//" in value or len(value) > 2048:
            raise ValueError("healthcheck.path 必须是合法的绝对 HTTP 路径")
        return value


class ResetConfig(BaseModel):
    method: Literal["POST"] = "POST"
    path: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value.startswith("/") or "//" in value or len(value) > 2048:
            raise ValueError("reset.path 必须是合法的绝对 HTTP 路径")
        return value


class RuntimeSection(BaseModel):
    protocol: RuntimeProtocol
    port: int | None = Field(default=None, ge=1, le=65535)
    command: list[str] | None = Field(default=None, min_length=1, max_length=64)
    healthcheck: HealthcheckConfig | None = None
    invoke_path: str = "/v1/evaluations/run"
    startup_timeout_seconds: int = Field(default=120, ge=1, le=600)
    case_timeout_seconds: int = Field(default=300, ge=1, le=3600)
    state_scope: Literal["case", "evaluation", "session"] = "case"
    reset: ResetConfig | None = None

    @field_validator("invoke_path")
    @classmethod
    def validate_invoke_path(cls, value: str) -> str:
        if not value.startswith("/") or "//" in value or len(value) > 2048:
            raise ValueError("invoke_path 必须是合法的绝对 HTTP 路径")
        return value

    @field_validator("command")
    @classmethod
    def validate_command(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and any(not item or len(item) > 4096 for item in value):
            raise ValueError("runtime.command 必须是非空 argv 数组")
        return value

    @model_validator(mode="after")
    def validate_protocol_requirements(self):
        if self.protocol == RuntimeProtocol.HTTP:
            if self.port is None:
                raise ValueError("HTTP 运行协议必须声明 port")
            if self.healthcheck is None:
                raise ValueError("HTTP 运行协议必须声明 healthcheck")
        elif not self.command:
            raise ValueError("CLI 运行协议必须声明 command argv")
        if self.state_scope == "evaluation" and self.reset is None:
            raise ValueError("evaluation 状态作用域必须声明 reset 接口")
        return self


class SecretBinding(BaseModel):
    target: str
    source: Literal["evaluation.llm_api_key"]

    @field_validator("target")
    @classmethod
    def validate_target(cls, value: str) -> str:
        if not _ENV_NAME.fullmatch(value):
            raise ValueError("secret target 必须是合法的大写环境变量名")
        if value in _PLATFORM_ENV:
            raise ValueError(f"secret target 不能覆盖平台保留环境变量: {value}")
        return value


class EnvironmentSection(BaseModel):
    public: dict[str, str] = Field(default_factory=dict)
    secret_refs: list[SecretBinding] = Field(default_factory=list, max_length=16)

    @field_validator("public")
    @classmethod
    def validate_public_environment(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 100:
            raise ValueError("公开环境变量不能超过 100 项")
        for key, item in value.items():
            if not _ENV_NAME.fullmatch(key) or len(item) > 4096 or "${" in item:
                raise ValueError(f"公开环境变量不合法: {key}")
            if any(marker in key for marker in ("KEY", "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL")):
                raise ValueError(f"疑似秘密字段必须使用 secret_refs: {key}")
            if key in _PLATFORM_ENV:
                raise ValueError(f"公开环境变量不能覆盖平台保留字段: {key}")
        return value


class NetworkSection(BaseModel):
    mode: Literal["none", "restricted"] = "none"
    allowed_domains: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("allowed_domains")
    @classmethod
    def validate_domains(cls, value: list[str]) -> list[str]:
        normalized = sorted({item.strip().lower() for item in value})
        if any(not item or len(item) > 253 or not _DOMAIN.fullmatch(item) for item in normalized):
            raise ValueError("allowed_domains 包含非法域名")
        return normalized

    @model_validator(mode="after")
    def validate_mode(self):
        if self.mode == "none" and self.allowed_domains:
            raise ValueError("network.mode 为 none 时不能声明 allowed_domains")
        return self


class RuntimeConfigUpload(BaseModel):
    schema_version: Literal[1] = 1
    entry_service: str = Field(min_length=1, max_length=63, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    runtime: RuntimeSection
    environment: EnvironmentSection = Field(default_factory=EnvironmentSection)
    network: NetworkSection = Field(default_factory=NetworkSection)


class SubmissionMetadata(BaseModel):
    agent_name: str = Field(min_length=1, max_length=255)
    version: str = Field(default="1.0.0", min_length=1, max_length=50)
    description: str = Field(min_length=30, max_length=20_000)
    agent_type: Literal["short_horizon", "long_horizon"]
    subtype: str | None = Field(default=None, max_length=50)
    llm_provider: str = Field(min_length=1, max_length=50)
    llm_model: str = Field(min_length=1, max_length=255)
    llm_api_base: str = Field(min_length=1, max_length=2048)
    enabled_tools: list[str] = Field(default_factory=list, max_length=100)
