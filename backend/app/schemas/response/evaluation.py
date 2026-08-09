from datetime import datetime
from pydantic import BaseModel


class DimensionScore(BaseModel):
    result: float = 0.0
    trajectory: float = 0.0
    efficiency: float = 0.0
    security: float = 0.0


class RadarChartData(BaseModel):
    dimensions: list[str] = []
    scores: list[float] = []
    benchmarks: list[float] = []


class ImprovementSuggestion(BaseModel):
    category: str
    severity: str
    description: str
    recommendation: str


class EvaluationReport(BaseModel):
    id: str
    submission_id: str
    status: str
    agent_type: str
    horizon: str
    overall_score: float | None = None
    grade: str | None = None
    dimensions: DimensionScore | None = None
    radar_chart_data: RadarChartData | None = None
    attribution: dict | None = None
    improvement_suggestions: list[ImprovementSuggestion] = []
    benchmark_comparison: dict | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class EvaluationSummary(BaseModel):
    id: str
    submission_id: str
    agent_name: str | None = None
    status: str
    agent_type: str
    overall_score: float | None = None
    grade: str | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True
