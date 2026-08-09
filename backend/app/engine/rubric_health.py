"""Rubric agreement monitoring and alert classification."""

from __future__ import annotations


class RubricHealthMonitor:
    def __init__(self, minimum_agreement: float = 0.85):
        if not 0 <= minimum_agreement <= 1:
            raise ValueError("minimum_agreement must be between 0 and 1")
        self.minimum_agreement = minimum_agreement

    def evaluate(self, judgments: list[tuple[str, str]]) -> dict:
        comparable = [(left, right) for left, right in judgments if left and right]
        agreements = sum(str(left).lower() == str(right).lower() for left, right in comparable)
        rate = agreements / len(comparable) if comparable else 1.0
        return {
            "samples": len(comparable),
            "agreements": agreements,
            "agreement_rate": round(rate, 4),
            "healthy": rate >= self.minimum_agreement,
            "alert": None if rate >= self.minimum_agreement else "rubric_judge_agreement_below_threshold",
        }


rubric_health_monitor = RubricHealthMonitor()
