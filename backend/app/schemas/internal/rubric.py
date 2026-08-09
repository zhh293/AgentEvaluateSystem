from enum import Enum
from pydantic import BaseModel, Field


class RubricDimension(str, Enum):
    RESULT = "result"
    TRAJECTORY = "trajectory"
    EFFICIENCY = "efficiency"
    SECURITY = "security"


class RubricVerdict(str, Enum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


class RubricItem(BaseModel):
    id: str
    dimension: RubricDimension
    metric: str
    description: str
    max_score: float = 1.0
    weight: float = 1.0
    depends_on: list[str] = []


class RubricSet(BaseModel):
    version: str = "1.0"
    agent_type: str
    horizon: str
    items: list[RubricItem] = []

    def total_weight(self) -> float:
        return sum(item.weight for item in self.items)
