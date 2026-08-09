from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.internal.trace import SpanType, TrajectoryData


class AttributionType(str, Enum):
    PLANNING_ERROR = "planning_error"
    TOOL_CALL_ERROR = "tool_call_error"
    SKILL_DEFECT = "skill_defect"
    ENVIRONMENT_ERROR = "environment_error"
    MODEL_INSUFFICIENT = "model_insufficient"


FIX_MAP = {
    AttributionType.PLANNING_ERROR: "调整 System Prompt 的任务拆解与依赖排序逻辑",
    AttributionType.TOOL_CALL_ERROR: "优化工具描述并增加参数 Schema 校验与示例",
    AttributionType.SKILL_DEFECT: "修复 Skill 实现并补充独立与回归测试",
    AttributionType.ENVIRONMENT_ERROR: "增加有界重试、超时、熔断和降级策略",
    AttributionType.MODEL_INSUFFICIENT: "使用更匹配的模型或增加高质量 Few-shot 示例",
}


class Attribution(BaseModel):
    type: AttributionType
    dimension: str
    metric: str
    score: float
    confidence: float = Field(ge=0, le=1)
    evidence_span_ids: list[str] = Field(default_factory=list)
    finding: str
    suggestion: str


def _infer_type(metric: str, trajectory: TrajectoryData) -> AttributionType:
    lower = metric.lower()
    if "plan" in lower or "规划" in lower:
        return AttributionType.PLANNING_ERROR
    if "tool" in lower or "parameter" in lower or "工具" in lower or "参数" in lower:
        return AttributionType.TOOL_CALL_ERROR
    if "skill" in lower:
        return AttributionType.SKILL_DEFECT
    errors = [span for span in trajectory.spans if span.status == "error" or span.error]
    if errors and any(span.span_type in {SpanType.EXTERNAL_API, SpanType.ENVIRONMENT_STATE_CHANGE} for span in errors):
        return AttributionType.ENVIRONMENT_ERROR
    return AttributionType.MODEL_INSUFFICIENT


def analyze_attributions(dimension_scores: dict, trajectory: TrajectoryData, agent_config=None, threshold: float = 70) -> list[Attribution]:
    result = []
    for dimension, value in dimension_scores.items():
        sub_scores = value if isinstance(value, dict) else {dimension: value}
        for metric, raw in sub_scores.items():
            score = raw.get("score") if isinstance(raw, dict) else raw
            if score is None or float(score) >= threshold:
                continue
            kind = _infer_type(metric, trajectory)
            related_types = {
                AttributionType.PLANNING_ERROR: {SpanType.AGENT_PLANNING, SpanType.AGENT_DECISION},
                AttributionType.TOOL_CALL_ERROR: {SpanType.TOOL_EXECUTION},
                AttributionType.SKILL_DEFECT: {SpanType.SKILL_EXECUTION},
                AttributionType.ENVIRONMENT_ERROR: {SpanType.EXTERNAL_API, SpanType.ENVIRONMENT_STATE_CHANGE},
                AttributionType.MODEL_INSUFFICIENT: {SpanType.LLM_CALL},
            }[kind]
            evidence = [span.span_id for span in trajectory.spans if span.span_type in related_types and (span.status == "error" or span.error)][:10]
            result.append(Attribution(type=kind, dimension=dimension, metric=metric, score=float(score), confidence=0.85 if evidence else 0.6, evidence_span_ids=evidence, finding=f"{dimension}.{metric} 得分 {float(score):.1f}，低于阈值 {threshold}", suggestion=FIX_MAP[kind]))
    return sorted(result, key=lambda item: item.score)
