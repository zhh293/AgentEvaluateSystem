from __future__ import annotations

import hashlib
import math

from app.engine.llm_judge import DualJudgeResult


def compute_human_machine_alignment(judge_results: list[DualJudgeResult], human_reviews: list[dict]) -> dict:
    reviews = {str(item["rubric_id"]): str(item["verdict"]).lower() for item in human_reviews}
    compared = agreed = 0
    for index, result in enumerate(judge_results):
        rubric_id = result.rubric_id or str(index)
        if rubric_id not in reviews or result.final_verdict is None:
            continue
        compared += 1
        agreed += result.final_verdict.value.lower() == reviews[rubric_id]
    rate = None if compared == 0 else agreed / compared
    return {"alignment_rate": rate, "alignment_percent": None if rate is None else round(rate * 100, 2), "compared": compared, "agreed": agreed, "threshold": 0.85, "automation_allowed": rate is not None and rate >= 0.85}


def deterministic_review_sample(items: list[dict], evaluation_id: str, rate: float = 0.1) -> list[dict]:
    if not items or rate <= 0:
        return []
    count = max(1, math.ceil(len(items) * min(rate, 1.0)))
    return sorted(items, key=lambda item: hashlib.sha256(f"{evaluation_id}:{item.get('rubric_id', '')}".encode()).digest())[:count]
