from enum import Enum
from pydantic import BaseModel, Field


class AgentType(str, Enum):
    SHORT = "short_horizon"
    LONG = "long_horizon"


class AgentSubtype(str, Enum):
    CONVERSATIONAL = "conversational"
    CODING = "coding"
    RAG = "rag"
    GUI = "gui"
    WORKFLOW = "workflow"
    CUSTOM = "custom"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LLMConfig(BaseModel):
    provider: str
    model: str
    api_base: str = ""
    api_key: str = ""
    max_output_tokens: int = 4096
    temperature: float = 0.7


class SkillConfig(BaseModel):
    name: str
    description: str
    tools: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.MEDIUM


class ToolConfig(BaseModel):
    name: str
    description: str
    risk_level: RiskLevel = RiskLevel.LOW


class AgentConfig(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    version: str = "1.0.0"
    type: AgentType
    subtype: AgentSubtype | None = None
    description: str = ""
    horizon: str | None = None
    llm: LLMConfig
    skills: list[SkillConfig] = Field(default_factory=list)
    tools: list[ToolConfig] = Field(default_factory=list)
    expected_input: dict = Field(default_factory=lambda: {"type": "text"})
    expected_output: dict = Field(default_factory=lambda: {"type": "text"})
    constraints: dict = Field(default_factory=dict)
    self_evaluation: dict = Field(default_factory=lambda: {"enabled": False, "max_retries": 3})
