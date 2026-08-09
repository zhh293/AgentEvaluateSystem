from pydantic import BaseModel, Field


class CreateTestCaseRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=100)
    agent_type: str
    horizon: str
    suite: str = "extended"
    tier: str = "extended"
    prompt: str = Field(min_length=1)
    context: dict | None = None
    expected_behavior: dict | None = None
    rubric: list[dict] = Field(default_factory=list)
    source: str = "manual"
