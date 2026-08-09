from pydantic import BaseModel


class TriggerEvaluationRequest(BaseModel):
    submission_id: str
    test_suites: list[str] = ["core"]
