from __future__ import annotations


class RegressionEngine:
    CHANGE_KEYS = ("llm_model", "skills", "system_prompt", "enabled_tools")

    def should_trigger_regression(self, submission, previous_submission) -> bool:
        if previous_submission is None:
            return True
        current = submission.config if hasattr(submission, "config") else submission
        previous = previous_submission.config if hasattr(previous_submission, "config") else previous_submission
        return any(current.get(key) != previous.get(key) for key in self.CHANGE_KEYS)

    def compare_with_baseline(self, current_results: dict, baseline_results: dict, tolerance: float = 0.05) -> dict:
        regressions = []
        for metric, baseline in baseline_results.items():
            if not isinstance(baseline, (int, float)):
                continue
            current = current_results.get(metric)
            if current is None or float(current) < float(baseline) * (1 - tolerance):
                regressions.append({"metric": metric, "baseline": baseline, "current": current, "minimum": baseline * (1 - tolerance)})
        return {"passed": not regressions, "regressions": regressions, "tolerance": tolerance}
