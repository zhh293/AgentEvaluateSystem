import logging
from dataclasses import dataclass
from enum import Enum

from app.engine.builtin_tools import BuiltinTool
from app.services.security_service import SecurityScanResult, Severity

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class RiskAssessment:
    level: RiskLevel
    reasons: list[str]


def assess_risk_level(
    enabled_tools: list[BuiltinTool],
    security_result: SecurityScanResult,
    agent_type: str = "",
) -> RiskAssessment:
    """评估 Agent 整体风险等级，决定后续沙箱隔离强度。

    评估维度：
      1. 安全扫描结果（代码层的危险模式匹配）
      2. 勾选工具的最高风险等级
      3. 中风险工具的数量累积
      4. Agent 类型（长程 Agent 天然风险更高）
    """
    reasons: list[str] = []

    # 1. 安全扫描 HIGH issue → 直接 HIGH
    high_security_issues = [i for i in security_result.issues if i.severity == Severity.HIGH]
    if high_security_issues:
        reasons.append(f"安全扫描发现 {len(high_security_issues)} 个高危问题")
        for i in high_security_issues[:3]:
            reasons.append(f"  [{i.code}] {i.file}:{i.line} — {i.message}")

    high_dep_vulns = [
        v for v in security_result.dependency_vulnerabilities
        if v.severity == Severity.HIGH.value
    ]
    if high_dep_vulns:
        reasons.append(f"依赖审计发现 {len(high_dep_vulns)} 个高危 CVE")
        for v in high_dep_vulns[:3]:
            reasons.append(f"  {v.package}: {v.cve} — {v.description}")

    if high_security_issues or high_dep_vulns:
        return RiskAssessment(level=RiskLevel.HIGH, reasons=reasons)

    # 2. 工具风险等级分析
    tool_high = [t for t in enabled_tools if t.risk_level == "high"]
    tool_medium = [t for t in enabled_tools if t.risk_level == "medium"]
    tool_low = [t for t in enabled_tools if t.risk_level == "low"]

    if tool_high:
        reasons.append(f"勾选了 {len(tool_high)} 个高风险工具: {[t.name for t in tool_high]}")
    if tool_medium:
        reasons.append(f"勾选了 {len(tool_medium)} 个中风险工具: {[t.name for t in tool_medium]}")

    # 3. 中等安全扫描问题
    medium_issues = [i for i in security_result.issues if i.severity == Severity.MEDIUM]
    if medium_issues:
        reasons.append(f"安全扫描发现 {len(medium_issues)} 个中等问题")

    # 综合判定
    if tool_high:
        return RiskAssessment(level=RiskLevel.MEDIUM, reasons=reasons)

    if len(tool_medium) >= 3 or (tool_medium and medium_issues):
        reasons.append("中风险工具累积 ≥3 或同时存在安全扫描中等问题")
        return RiskAssessment(level=RiskLevel.MEDIUM, reasons=reasons)

    # 4. 长程 Agent 天然风险较高
    if agent_type == "long_horizon" and (tool_medium or medium_issues):
        reasons.append("长程 Agent 存在中风险工具或安全问题，风险上调")
        return RiskAssessment(level=RiskLevel.MEDIUM, reasons=reasons)

    # 纯对话/检索类（仅 low 风险工具 + 无安全扫描问题）→ LOW
    reasons.append("仅使用低风险工具且安全扫描通过")
    return RiskAssessment(level=RiskLevel.LOW, reasons=reasons)
