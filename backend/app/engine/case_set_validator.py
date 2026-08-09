from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.schemas.internal.case_set import GeneratedCase


@dataclass(frozen=True)
class CaseSetValidation:
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    coverage: dict[str, Any]
    content_digest: str


def validate_case_set(
    cases: list[GeneratedCase], capability_map: dict[str, dict[str, Any]], target_count: int,
    entry_service: str | None = None,
) -> CaseSetValidation:
    errors: list[str] = []
    warnings: list[str] = []
    if not cases:
        errors.append("Case Set 不能为空")
    if len(cases) > 60:
        errors.append("Case Set 不能超过 60 条")
    minimum = min(30, max(len(capability_map), target_count))
    if len(cases) < minimum:
        errors.append(f"Case 数量不足，要求至少 {minimum} 条，实际 {len(cases)} 条")
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        errors.append("Case ID 存在重复")

    coverage: dict[str, list[str]] = {key: [] for key in capability_map}
    signatures: dict[str, str] = {}
    for case in cases:
        if entry_service and case.invocation.service != entry_service:
            errors.append(f"{case.id} 必须调用入口服务 {entry_service}")
        unknown = sorted(set(case.capability_ids) - set(capability_map))
        if unknown:
            errors.append(f"{case.id} 引用了不存在的 Capability: {', '.join(unknown)}")
        for capability_id in set(case.capability_ids).intersection(capability_map):
            coverage[capability_id].append(case.id)
            capability = capability_map[capability_id]
            operation = capability["operation"]
            if case.invocation.protocol != capability["kind"]:
                errors.append(f"{case.id} 调用协议与 Capability {capability_id} 不一致")
            if capability["kind"] == "http":
                if case.invocation.method != operation["method"] or case.invocation.path != operation["path"]:
                    errors.append(f"{case.id} 的 HTTP 调用与 Capability {capability_id} 不一致")
            elif capability["kind"] == "cli":
                expected = list(operation.get("executable", [])) + list(operation.get("args", []))
                if case.invocation.argv is None or case.invocation.argv[:len(expected)] != expected:
                    errors.append(f"{case.id} 的 CLI argv 与 Capability {capability_id} 不一致")
        signature = _signature(case)
        if signature in signatures:
            errors.append(f"Case 调用重复: {signatures[signature]} 与 {case.id}")
        signatures[signature] = case.id
        for rubric in case.rubrics:
            if rubric.judge_type == "llm_judge" and not rubric.evidence_required:
                errors.append(f"{case.id}/{rubric.id} 的 LLM Rubric 缺少证据要求")
            if rubric.critical and rubric.dimension != "security":
                warnings.append(f"{case.id}/{rubric.id} 是非安全维度 critical Rubric，请人工确认")
            declared = set(rubric.evidence_required)
            referenced = _condition_paths(rubric.pass_condition)
            invalid_pointers = sorted(pointer for pointer in declared if pointer.split(".", 1)[0] not in {"result", "http", "cli", "output", "trace"})
            if invalid_pointers:
                errors.append(f"{case.id}/{rubric.id} 声明了非法 Evidence Pointer: {', '.join(invalid_pointers)}")
            if rubric.judge_type in {"programmatic", "rule_engine"} and not referenced.issubset(declared):
                errors.append(f"{case.id}/{rubric.id} 的 pass_condition 引用了未声明证据: {', '.join(sorted(referenced - declared))}")

    uncovered = sorted(key for key, value in coverage.items() if not value)
    if uncovered:
        errors.append(f"存在未覆盖 Capability: {', '.join(uncovered)}")
    suite_counts: dict[str, int] = {}
    for case in cases:
        suite_counts[case.suite] = suite_counts.get(case.suite, 0) + 1
    if cases and suite_counts.get("security", 0) / len(cases) < 0.1:
        warnings.append("安全 Case 占比低于 10%")
    payload = [case.model_dump(mode="json") for case in sorted(cases, key=lambda item: item.id)]
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    return CaseSetValidation(
        valid=not errors, errors=tuple(errors), warnings=tuple(warnings),
        coverage={
            "capabilities": coverage,
            "covered": len(coverage) - len(uncovered),
            "total": len(coverage),
            "coverage_rate": 1.0 if not coverage else (len(coverage) - len(uncovered)) / len(coverage),
            "suite_counts": suite_counts,
        },
        content_digest=digest,
    )


def recommended_case_count(capability_count: int, horizon: str) -> int:
    base = max(30, capability_count * 3)
    if horizon == "long":
        base = max(base, 40)
    return min(60, base)


def _signature(case: GeneratedCase) -> str:
    invocation = case.invocation.model_dump(mode="json")
    normalized = {"capabilities": sorted(case.capability_ids), "invocation": invocation, "suite": case.suite}
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _condition_paths(condition: Any) -> set[str]:
    if not isinstance(condition, dict):
        return set()
    paths = {condition["path"]} if isinstance(condition.get("path"), str) else set()
    for key in ("all", "any"):
        if isinstance(condition.get(key), list):
            for child in condition[key]:
                paths.update(_condition_paths(child))
    return paths
