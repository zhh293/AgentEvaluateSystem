from enum import Enum

from pydantic import BaseModel, Field, field_validator


class RubricDimension(str, Enum):
    RESULT = "result"
    TRAJECTORY = "trajectory"
    EFFICIENCY = "efficiency"
    SECURITY = "security"


class RubricSource(str, Enum):
    BUILTIN = "builtin"
    CONFIG_DERIVED = "config"
    AI_GENERATED = "ai_gen"
    CASE_PARSED = "case_parsed"


class RubricCheckType(str, Enum):
    PROGRAMMATIC = "programmatic"
    LLM_JUDGE = "llm_judge"
    RULE_ENGINE = "rule_engine"


class RubricVerdict(str, Enum):
    YES = "Yes"
    NO = "No"
    UNKNOWN = "Unknown"


class RubricItem(BaseModel):
    id: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=4)
    dimension: RubricDimension
    check_type: RubricCheckType
    source: RubricSource
    verdict_type: str = "binary"
    pass_condition: str = Field(min_length=5)
    metric: str = ""
    max_score: float = Field(default=1.0, gt=0)
    weight: float = Field(default=1.0, gt=0)
    depends_on: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    @field_validator("verdict_type")
    @classmethod
    def validate_verdict_type(cls, value: str) -> str:
        if value not in {"binary", "ternary"}:
            raise ValueError("verdict_type must be binary or ternary")
        return value


Rubric = RubricItem


class RubricSet(BaseModel):
    version: str = "1.0"
    agent_type: str
    horizon: str
    items: list[RubricItem] = Field(default_factory=list)

    def total_weight(self) -> float:
        return sum(item.weight for item in self.items)
