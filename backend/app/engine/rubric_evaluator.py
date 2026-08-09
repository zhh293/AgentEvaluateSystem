from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.engine.llm_judge import AIJudge, dual_judge_rubric
from app.schemas.internal.rubric import RubricVerdict
from app.schemas.internal.trace import SpanData, SpanType


@dataclass(frozen=True)
class RubricEvaluation:
    rubric_id: str
    dimension: str
    verdict: str
    score: float | None
    weight: float
    critical: bool
    judge_type: str
    evidence: list[dict[str, Any]]
    details: dict[str, Any]


async def evaluate_rubric(rubric: dict[str, Any], evidence: dict[str, Any], spans: list[SpanData]) -> RubricEvaluation:
    judge_type = rubric["judge_type"]
    if judge_type in {"programmatic", "rule_engine"}:
        verdict, used, reason = _evaluate_condition(rubric["pass_condition"], evidence)
        return _result(rubric, verdict, used, {"reason": reason})
    if not settings.JUDGE_API_KEY:
        return _result(rubric, "unknown", [], {"reason": "LLM Judge 未配置"})
    context = list(spans)
    if not any(span.span_id == "platform-result-evidence" for span in context):
        context.append(SpanData(
            span_id="platform-result-evidence", span_type=SpanType.AGENT_EXECUTION,
            operation="case_result",
            output={key: value for key, value in evidence.items() if key != "trace"},
        ))
    judge_a = AIJudge(settings.JUDGE_MODEL_A, settings.JUDGE_API_KEY, settings.JUDGE_API_BASE)
    judge_b = AIJudge(settings.JUDGE_MODEL_B, settings.JUDGE_API_KEY, settings.JUDGE_API_BASE)
    judged = await dual_judge_rubric(
        {"id": rubric["id"], "description": rubric["assertion"], "pass_condition": rubric["pass_condition"]},
        context, judge_a, judge_b,
    )
    if judged.final_verdict is None:
        return _result(rubric, "unknown", [], {"agreement": judged.agreement_level, "needs_human_review": True})
    mapping = {RubricVerdict.YES: "pass", RubricVerdict.NO: "fail", RubricVerdict.UNKNOWN: "unknown"}
    items = []
    for judge in (judged.judge_a, judged.judge_b, judged.judge_c):
        if judge:
            items.extend({"span_id": item.span_id, "quote": item.quote} for item in judge.evidence)
    return _result(rubric, mapping[judged.final_verdict], items, {
        "agreement": judged.agreement_level, "arbitrated": judged.arbitrated,
        "judge_scores": [judged.judge_a.score, judged.judge_b.score] + ([judged.judge_c.score] if judged.judge_c else []),
    })


def _result(rubric: dict, verdict: str, evidence: list, details: dict) -> RubricEvaluation:
    return RubricEvaluation(
        rubric_id=rubric["id"], dimension=rubric["dimension"], verdict=verdict,
        score=100.0 if verdict == "pass" else 0.0 if verdict == "fail" else None,
        weight=float(rubric.get("weight", 1.0)), critical=bool(rubric.get("critical", False)),
        judge_type=rubric["judge_type"], evidence=evidence, details=details,
    )


def _evaluate_condition(condition: Any, evidence: dict[str, Any]) -> tuple[str, list[dict], str]:
    if not isinstance(condition, dict):
        return "unknown", [], "程序化 Rubric 的 pass_condition 必须是结构化对象"
    if "all" in condition:
        children = [_evaluate_condition(item, evidence) for item in condition["all"]]
        return _combine(children, require_all=True)
    if "any" in condition:
        children = [_evaluate_condition(item, evidence) for item in condition["any"]]
        return _combine(children, require_all=False)
    pointer, operator = condition.get("path"), condition.get("operator")
    if not isinstance(pointer, str) or not isinstance(operator, str):
        return "unknown", [], "条件缺少 path/operator"
    exists, actual = _resolve(evidence, pointer)
    if not exists:
        return "unknown", [], f"证据不存在: {pointer}"
    expected = condition.get("value")
    operations = {
        "eq": lambda: actual == expected,
        "ne": lambda: actual != expected,
        "in": lambda: actual in expected if isinstance(expected, list) else False,
        "not_in": lambda: actual not in expected if isinstance(expected, list) else False,
        "not_empty": lambda: actual is not None and actual != "" and actual != [] and actual != {},
        "empty": lambda: actual is None or actual == "" or actual == [] or actual == {},
        "gte": lambda: actual >= expected,
        "lte": lambda: actual <= expected,
        "contains": lambda: expected in actual,
        "exists": lambda: exists,
    }
    if operator not in operations:
        return "unknown", [], f"不支持的 operator: {operator}"
    try:
        passed = bool(operations[operator]())
    except (TypeError, ValueError):
        return "unknown", [], f"证据类型无法执行 operator: {operator}"
    return ("pass" if passed else "fail"), [{"pointer": pointer, "value": actual}], "条件满足" if passed else "条件不满足"


def _combine(children: list[tuple[str, list[dict], str]], require_all: bool) -> tuple[str, list[dict], str]:
    verdicts = [item[0] for item in children]
    evidence = [entry for item in children for entry in item[1]]
    if require_all:
        if "fail" in verdicts:
            return "fail", evidence, "all 条件中存在失败项"
        if "unknown" in verdicts:
            return "unknown", evidence, "all 条件中存在未知项"
        return "pass", evidence, "全部条件满足"
    if "pass" in verdicts:
        return "pass", evidence, "any 条件中存在通过项"
    if "unknown" in verdicts:
        return "unknown", evidence, "any 条件没有通过项且存在未知项"
    return "fail", evidence, "全部候选条件失败"


def _resolve(payload: Any, pointer: str) -> tuple[bool, Any]:
    current = payload
    for part in pointer.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return False, None
    return True, current
