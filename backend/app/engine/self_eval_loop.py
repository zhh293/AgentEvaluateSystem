from __future__ import annotations

import copy
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

from app.engine.attribution import Attribution, AttributionType


@dataclass
class CorrectionResult:
    applied: bool
    config: dict
    description: str
    requires_human: bool = False


class AutoCorrector:
    def apply_correction(self, attribution: Attribution, agent_config: dict) -> CorrectionResult:
        updated = copy.deepcopy(agent_config)
        if attribution.type == AttributionType.PLANNING_ERROR:
            addition = "\n执行复杂任务前先列出有序步骤，确认依赖后逐步执行，并在每步后校验结果。"
            updated["system_prompt"] = updated.get("system_prompt", "") + addition
            return CorrectionResult(True, updated, "增加显式任务拆解、依赖排序和逐步校验指令")
        if attribution.type == AttributionType.TOOL_CALL_ERROR:
            updated.setdefault("tool_policy", {})["validate_arguments"] = True
            updated["tool_policy"]["reject_unknown_tools"] = True
            return CorrectionResult(True, updated, "启用工具参数校验和未知工具拒绝策略")
        if attribution.type == AttributionType.ENVIRONMENT_ERROR:
            updated["retry"] = {"max_attempts": 3, "backoff": "exponential", "base_seconds": 1}
            updated["timeout_seconds"] = max(int(updated.get("timeout_seconds", 30)), 30)
            return CorrectionResult(True, updated, "增加有界指数退避与超时配置")
        return CorrectionResult(False, updated, "该归因需要开发者或模型选择决策", True)


def _verdict(value) -> str:
    if isinstance(value, dict):
        value = value.get("verdict")
    return str(getattr(value, "value", value)).lower()


def check_degradation(rubrics_before: dict, rubrics_after: dict) -> dict:
    degraded, warnings, improved, still_failing, missing = [], [], [], [], []
    for rubric_id, before in rubrics_before.items():
        if rubric_id not in rubrics_after:
            missing.append(rubric_id)
            continue
        left, right = _verdict(before), _verdict(rubrics_after[rubric_id])
        if left == "yes" and right == "no":
            degraded.append(rubric_id)
        elif left == "yes" and right == "unknown":
            warnings.append(rubric_id)
        elif left in {"no", "unknown"} and right == "yes":
            improved.append(rubric_id)
        elif left == "no" and right == "no":
            still_failing.append(rubric_id)
    return {"passed": not degraded and not missing, "degraded": degraded, "warnings": warnings, "improved": improved, "still_failing": still_failing, "missing": missing}


class SelfEvalLoop:
    def __init__(self, max_retries: int = 3, corrector: AutoCorrector | None = None):
        if not 0 <= max_retries <= 10:
            raise ValueError("max_retries must be between 0 and 10")
        self.max_retries = max_retries
        self.corrector = corrector or AutoCorrector()

    async def run(self, initial_config: dict, evaluate: Callable[[dict], Any], attribute: Callable[[dict], list[Attribution]]) -> dict:
        config = copy.deepcopy(initial_config)
        attempts = []
        baseline_rubrics = None
        best = None
        # Initial attempt plus max_retries corrections.
        for attempt_number in range(1, self.max_retries + 2):
            evaluation = evaluate(config)
            if inspect.isawaitable(evaluation):
                evaluation = await evaluation
            record = {"attempt": attempt_number, "score": float(evaluation.get("score", 0)), "rubrics": evaluation.get("rubrics", {}), "config": copy.deepcopy(config), "corrections": []}
            if baseline_rubrics is not None:
                record["degradation"] = check_degradation(baseline_rubrics, record["rubrics"])
                if not record["degradation"]["passed"]:
                    record["rolled_back"] = True
                    attempts.append(record)
                    break
            attempts.append(record)
            if best is None or record["score"] > best["score"]:
                best = record
            if record["rubrics"] and all(_verdict(value) == "yes" for value in record["rubrics"].values()):
                return {"status": "passed", "best_attempt": record, "attempts": attempts, "final_config": config}
            if attempt_number > self.max_retries:
                break
            attributions = attribute(evaluation)
            baseline_rubrics = record["rubrics"]
            changed = False
            for item in attributions:
                correction = self.corrector.apply_correction(item, config)
                record["corrections"].append({"applied": correction.applied, "description": correction.description, "requires_human": correction.requires_human})
                if correction.applied:
                    config, changed = correction.config, True
            if not changed:
                break
        return degrade_gracefully(attempts, best)


def degrade_gracefully(attempts: list[dict], best: dict | None = None) -> dict:
    best = best or (max(attempts, key=lambda item: item.get("score", 0)) if attempts else None)
    failed = [] if best is None else [rubric_id for rubric_id, result in best.get("rubrics", {}).items() if _verdict(result) != "yes"]
    return {"status": "needs_human_intervention", "best_attempt": best, "attempts": attempts, "failed_rubrics": failed, "final_config": None if best is None else best.get("config")}
