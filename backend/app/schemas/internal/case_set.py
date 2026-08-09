from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class EvidenceRequirement(BaseModel):
    pointer: str = Field(min_length=1, max_length=500)


class CaseRubric(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    dimension: Literal["result", "trajectory", "efficiency", "security"]
    assertion: str = Field(min_length=5, max_length=2000)
    judge_type: Literal["programmatic", "rule_engine", "llm_judge"]
    evidence_required: list[str] = Field(min_length=1, max_length=20)
    pass_condition: dict[str, Any] | str
    weight: float = Field(default=1.0, gt=0, le=10)
    critical: bool = False


class CaseInvocation(BaseModel):
    protocol: Literal["http", "cli"]
    service: str = Field(min_length=1, max_length=63)
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"] | None = None
    path: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None
    argv: list[str] | None = None
    stdin: str | None = None

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, value: dict[str, str]) -> dict[str, str]:
        forbidden = {"authorization", "proxy-authorization", "cookie", "set-cookie", "host"}
        if any(key.lower() in forbidden for key in value):
            raise ValueError("Case 不能内嵌认证、Cookie 或 Host Header")
        if len(value) > 50 or any(len(key) > 100 or len(item) > 4096 for key, item in value.items()):
            raise ValueError("Case Header 数量或长度超过限制")
        return value

    @field_validator("argv")
    @classmethod
    def validate_argv(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and (len(value) > 64 or any(not item or len(item) > 4096 for item in value)):
            raise ValueError("CLI argv 不合法")
        return value

    @model_validator(mode="after")
    def validate_protocol(self):
        if self.protocol == "http":
            if not self.method or not self.path or not self.path.startswith("/") or "//" in self.path:
                raise ValueError("HTTP Case 必须声明 method 和绝对 path")
            if self.argv is not None:
                raise ValueError("HTTP Case 不能声明 argv")
        else:
            if not self.argv:
                raise ValueError("CLI Case 必须声明非空 argv")
            if self.method or self.path:
                raise ValueError("CLI Case 不能声明 method/path")
        return self


class GeneratedCase(BaseModel):
    id: str = Field(min_length=1, max_length=150)
    title: str = Field(min_length=5, max_length=500)
    suite: Literal["functional", "boundary", "recovery", "security", "efficiency"]
    horizon: Literal["short", "long"]
    capability_ids: list[str] = Field(min_length=1, max_length=20)
    setup: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    invocation: CaseInvocation
    constraints: dict[str, Any] = Field(default_factory=dict)
    rubrics: list[CaseRubric] = Field(min_length=1, max_length=20)

    @field_validator("rubrics")
    @classmethod
    def unique_rubrics(cls, value: list[CaseRubric]) -> list[CaseRubric]:
        ids = [item.id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("Case 内 Rubric ID 重复")
        if not any(item.dimension == "result" for item in value):
            raise ValueError("每个 Case 至少需要一条 result Rubric")
        return value


class CandidateCaseSet(BaseModel):
    cases: list[GeneratedCase]
