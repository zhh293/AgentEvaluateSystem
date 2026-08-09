from __future__ import annotations

from app.core.exceptions import ValidationException


class QualityGateEngine:
    GATES = {
        "skill_launch": {"suite": "core", "requirements": {"pass_rate": 90}},
        "model_switch": {"suite": "regression", "requirements": {"baseline_retention": 95}},
        "prompt_change": {"suite": "core", "requirements": {"core_pass_rate": 100}},
        "ops_monitor": {"suite": "production_sample", "requirements": {"success_rate": 85, "satisfaction": 4.0}},
    }

    def check_gate(self, gate_type: str, metrics: dict) -> dict:
        if gate_type not in self.GATES:
            raise ValidationException(f"未知门禁类型: {gate_type}")
        requirements = self.GATES[gate_type]["requirements"]
        checks = {name: {"actual": metrics.get(name), "required": minimum, "passed": metrics.get(name) is not None and float(metrics[name]) >= minimum} for name, minimum in requirements.items()}
        return {"gate_type": gate_type, "suite": self.GATES[gate_type]["suite"], "passed": all(item["passed"] for item in checks.values()), "checks": checks}
