from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.engine.aggregator import aggregate_score
from app.engine.attribution import Attribution
from app.infrastructure.minio import MinIOClient, minio_client


def generate_radar_data(dimension_scores: dict[str, float], benchmarks: dict[str, float] | None = None) -> dict:
    dimensions = ["result", "trajectory", "efficiency", "security"]
    return {"dimensions": dimensions, "scores": [float(dimension_scores[name]) for name in dimensions], "benchmarks": [float((benchmarks or {}).get(name, 0)) for name in dimensions]}


def compute_benchmark(overall_score: float, historical_scores: list[float] | None = None, baseline_score: float | None = None) -> dict:
    history = sorted(float(score) for score in (historical_scores or []))
    percentile = None if not history else round(100 * sum(score <= overall_score for score in history) / len(history), 2)
    rank = None if not history else 1 + sum(score > overall_score for score in history)
    return {"sample_size": len(history), "percentile": percentile, "leaderboard_rank": rank, "vs_baseline": None if baseline_score in (None, 0) else round((overall_score - baseline_score) / baseline_score * 100, 2)}


class ReportService:
    def __init__(self, storage: MinIOClient = minio_client):
        self.storage = storage

    def generate_report(self, *, evaluation_id: str, submission_id: str, agent_name: str, agent_type: str, agent_version: str, horizon: str, dimension_scores: dict[str, float], attributions: list[Attribution] | None = None, skill_results: list[dict] | None = None, self_eval_loops: list[dict] | None = None, historical_scores: list[float] | None = None, baseline_score: float | None = None, dimension_benchmarks: dict[str, float] | None = None) -> dict[str, Any]:
        aggregate = aggregate_score(dimension_scores, horizon)
        attribution_payload = [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in (attributions or [])]
        suggestions = [{"severity": "high" if item["score"] < 50 else "medium", "dimension": item["dimension"], "finding": item["finding"], "evidence_span_ids": item.get("evidence_span_ids", []), "suggestion": item["suggestion"]} for item in attribution_payload]
        return {
            "report_id": str(uuid.uuid4()),
            "evaluation_id": evaluation_id,
            "submission_id": submission_id,
            "agent_name": agent_name,
            "agent_type": agent_type,
            "agent_version": agent_version,
            "horizon": horizon,
            "overall_score": aggregate["overall_score"],
            "grade": aggregate["grade"],
            "dimensions": dimension_scores,
            "weights": aggregate["weights"],
            "skill_evaluation": {"skills": skill_results or []},
            "attribution": attribution_payload,
            "improvement_suggestions": suggestions,
            "self_evaluation_loop": {"iterations": self_eval_loops or []},
            "radar_chart_data": generate_radar_data(dimension_scores, dimension_benchmarks),
            "benchmark_comparison": compute_benchmark(aggregate["overall_score"], historical_scores, baseline_score),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def store_report(self, evaluation_id: str, report: dict) -> str:
        return self.storage.upload_json(f"reports/{evaluation_id}/report.json", report)


report_service = ReportService()
