from __future__ import annotations


SHORT_HORIZON_WEIGHTS = {"result": 0.40, "trajectory": 0.20, "efficiency": 0.20, "security": 0.20}
LONG_HORIZON_WEIGHTS = {"result": 0.30, "trajectory": 0.30, "efficiency": 0.20, "security": 0.20}


def score_to_grade(score: float) -> str:
    for minimum, grade in [(93, "A+"), (87, "A"), (83, "A-"), (78, "B+"), (73, "B"), (68, "B-"), (63, "C+"), (60, "C")]:
        if score >= minimum:
            return grade
    return "D"


def aggregate_score(dimension_scores: dict[str, float], horizon: str) -> dict:
    weights = LONG_HORIZON_WEIGHTS if horizon == "long" else SHORT_HORIZON_WEIGHTS
    missing = set(weights) - set(dimension_scores)
    if missing:
        raise ValueError(f"missing dimension scores: {sorted(missing)}")
    invalid = {name: value for name, value in dimension_scores.items() if name in weights and (value is None or not 0 <= float(value) <= 100)}
    if invalid:
        raise ValueError(f"dimension scores must be between 0 and 100: {invalid}")
    total = sum(float(dimension_scores[name]) * weight for name, weight in weights.items())
    return {"overall_score": round(total, 1), "grade": score_to_grade(total), "dimensions": {name: float(dimension_scores[name]) for name in weights}, "weights": weights}


def aggregate_rubrics(rubric_results: list[dict]) -> dict[str, float]:
    grouped: dict[str, list[tuple[float, float]]] = {}
    for result in rubric_results:
        if result.get("score") is None:
            continue
        grouped.setdefault(result["dimension"], []).append((float(result["score"]), float(result.get("weight", 1))))
    return {dimension: round(sum(score * weight for score, weight in values) / sum(weight for _, weight in values), 2) for dimension, values in grouped.items() if sum(weight for _, weight in values) > 0}
