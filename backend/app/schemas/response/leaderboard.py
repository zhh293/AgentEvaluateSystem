from pydantic import BaseModel


class LeaderboardEntry(BaseModel):
    rank: int
    submission_id: str
    agent_name: str
    version: str
    agent_type: str
    overall_score: float
    grade: str
    dimensions: dict


class LeaderboardResponse(BaseModel):
    entries: list[LeaderboardEntry]
    total: int
    benchmark_count: int
