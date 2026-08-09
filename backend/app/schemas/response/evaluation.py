from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class DimensionScore(BaseModel):
    result: float | None = None
    trajectory: float | None = None
    efficiency: float | None = None
    security: float | None = None


class RadarChartData(BaseModel):
    dimensions: list[str] = Field(default_factory=list)
    scores: list[float] = Field(default_factory=list)
    benchmarks: list[float] = Field(default_factory=list)


class ImprovementSuggestion(BaseModel):
    category: str
    severity: str
    description: str
    recommendation: str


class EvaluationReport(BaseModel):
    id: UUID
    submission_id: UUID
    status: str
    agent_type: str
    horizon: str
    overall_score: float | None = None
    grade: str | None = None
    dimensions: DimensionScore | None = None
    radar_chart_data: RadarChartData | None = None
    attribution: dict | None = None
    improvement_suggestions: list[ImprovementSuggestion] = Field(default_factory=list)
    benchmark_comparison: dict | None = None
    report_full: dict | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class EvaluationSummary(BaseModel):
    id: UUID
    submission_id: UUID
    agent_name: str | None = None
    status: str
    agent_type: str
    overall_score: float | None = None
    grade: str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
