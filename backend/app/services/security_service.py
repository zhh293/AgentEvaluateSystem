import logging
import re
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ScanStatus(str, Enum):
    PASSED = "passed"
    REJECTED = "rejected"
    VALIDATED_WITH_WARNINGS = "validated_with_warnings"


@dataclass
class SecurityIssue:
    severity: Severity
    file: str
    line: int
    code: str
    message: str


@dataclass
class DependencyVulnerability:
    package: str
    version: str
    cve: str
    severity: str
    description: str


@dataclass
class SecurityScanResult:
    status: ScanStatus
    issues: list[SecurityIssue] = field(default_factory=list)
    dependency_vulnerabilities: list[DependencyVulnerability] = field(default_factory=list)


class SecurityScanner:
    """静态安全扫描 + 依赖漏洞审计

    对提交的 Agent 源码执行 Bandit 风格 AST 级扫描和 Safety 依赖审计。
    HIGH 风险 → 拒绝提交，MEDIUM → 接受但标记，LOW → 放行。
    """

    MAX_FILE_LINES = 5000

    DANGEROUS_PATTERNS: list[tuple[str, str, str, str]] = [
        # (pattern, code, severity, message)
        (r'\bos\.system\s*\(', "B602", Severity.HIGH, "os.system() 执行任意系统命令"),
        (r'\bsubprocess\.(call|Popen|run|check_call|check_output)\s*\(', "B603", Severity.HIGH, "subprocess 执行外部命令"),
        (r'\beval\s*\(', "B307", Severity.HIGH, "eval() 存在代码注入风险"),
        (r'\bexec\s*\(', "B102", Severity.HIGH, "exec() 执行动态代码"),
        (r'\bcompile\s*\(', "B103", Severity.MEDIUM, "compile() 可能存在代码注入"),
        (r'__import__\s*\(', "B108", Severity.MEDIUM, "__import__() 动态导入需审计"),
        (r'\bimportlib\.import_module\s*\(', "B110", Severity.MEDIUM, "动态模块导入需审计来源"),
        (r'\bsocket\.socket\s*\(', "B405", Severity.MEDIUM, "socket 网络连接需确认白名单"),
        (r'\bopen\s*\([^)]*[\'"][wa]', "B108", Severity.MEDIUM, "文件写入操作需审计"),
        (r'\bshutil\.(copy|move|rmtree)\s*\(', "B109", Severity.LOW, "文件系统操作"),
        (r'\bos\.(remove|unlink|rmdir|chmod|chown)\s*\(', "B110", Severity.LOW, "文件系统敏感操作"),
        (r'\bpickle\.(load|dump)\s*\(', "B301", Severity.HIGH, "pickle 反序列化存在 RCE 风险"),
        (r'\bmarshal\.(load|dump)\s*\(', "B302", Severity.MEDIUM, "marshal 反序列化不安全"),
        (r'\byaml\.load\s*\((?!.*Loader)', "B506", Severity.HIGH, "yaml.load() 应改用 yaml.safe_load()"),
        (r'\bctypes\.(CDLL|WinDLL)\s*\(', "B411", Severity.HIGH, "ctypes 加载动态库存在风险"),
        (r'\bhttp\.server\s*\(', "B501", Severity.MEDIUM, "启动 HTTP 服务需审计"),
        (r'\bftp\b.*\b(login|storbinary|retrbinary)', "B502", Severity.MEDIUM, "FTP 协议使用需审计"),
        (r'\btelnetlib\b', "B503", Severity.MEDIUM, "Telnet 明文协议应避免使用"),
    ]

    def scan_source(self, source_dir: str | Path) -> SecurityScanResult:
        """扫描 Agent 源码目录中所有 Python 文件的静态安全问题"""
        source_path = Path(source_dir)
        issues: list[SecurityIssue] = []

        if not source_path.exists():
            return SecurityScanResult(
                status=ScanStatus.REJECTED,
                issues=[SecurityIssue(
                    severity=Severity.HIGH, file="", line=0,
                    code="SCAN001", message=f"源码目录不存在: {source_dir}",
                )],
            )

        py_files = list(source_path.rglob("*.py"))
        if not py_files:
            logger.info("未找到 Python 文件，跳过静态扫描")
            return SecurityScanResult(status=ScanStatus.PASSED)

        for py_file in py_files:
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            rel_path = str(py_file.relative_to(source_path))
            lines = content.split("\n")

            if len(lines) > self.MAX_FILE_LINES:
                issues.append(SecurityIssue(
                    severity=Severity.MEDIUM, file=rel_path, line=len(lines),
                    code="SIZE001",
                    message=f"文件 {len(lines)} 行超过上限 {self.MAX_FILE_LINES}",
                ))

            for i, line in enumerate(lines, start=1):
                stripped = line.strip()
                if stripped.startswith("#") or not stripped:
                    continue
                for pattern, code, severity, msg in self.DANGEROUS_PATTERNS:
                    if re.search(pattern, stripped):
                        issues.append(SecurityIssue(
                            severity=severity, file=rel_path, line=i,
                            code=code, message=msg,
                        ))

        has_high = any(i.severity == Severity.HIGH for i in issues)
        if has_high:
            status = ScanStatus.REJECTED
        elif issues:
            status = ScanStatus.VALIDATED_WITH_WARNINGS
        else:
            status = ScanStatus.PASSED

        logger.info("安全扫描完成: status=%s issues=%d", status.value, len(issues))
        return SecurityScanResult(status=status, issues=issues)

    def audit_dependencies(self, requirements_content: str) -> list[DependencyVulnerability]:
        """Audit pinned dependencies against PyPI/OSV through pip-audit.

        Unlike the former hard-coded table, results carry real advisory IDs and
        are updated by the vulnerability service. Unpinned requirements are
        rejected from auditing because assigning them an arbitrary version would
        produce misleading results.
        """
        if not requirements_content.strip():
            return []
        with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as req:
            req.write(requirements_content)
            req_path = req.name
        try:
            process = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip_audit",
                    "-r",
                    req_path,
                    "--format",
                    "json",
                    "--progress-spinner",
                    "off",
                    "--timeout",
                    "15",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                check=False,
            )
            # pip-audit returns 1 when vulnerabilities are found; both 0 and 1
            # contain a valid JSON report.
            if process.returncode not in (0, 1):
                logger.warning("pip-audit unavailable: %s", process.stderr[-500:])
                return []
            report = json.loads(process.stdout or "[]")
            dependencies = report.get("dependencies", []) if isinstance(report, dict) else report
            vulnerabilities: list[DependencyVulnerability] = []
            for dependency in dependencies:
                for advisory in dependency.get("vulns", []):
                    aliases = advisory.get("aliases") or []
                    advisory_id = next((item for item in aliases if item.startswith("CVE-")), advisory.get("id", "UNKNOWN"))
                    vulnerabilities.append(
                        DependencyVulnerability(
                            package=dependency.get("name", "unknown"),
                            version=dependency.get("version", ""),
                            cve=advisory_id,
                            # pip-audit/OSV does not guarantee CVSS in JSON; a
                            # known vulnerable resolved dependency blocks intake.
                            severity=Severity.HIGH.value,
                            description=advisory.get("description") or "; ".join(advisory.get("fix_versions", [])) or advisory_id,
                        )
                    )
            return vulnerabilities
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            logger.warning("dependency audit failed: %s", exc)
            return []
        finally:
            Path(req_path).unlink(missing_ok=True)

    def full_audit(self, source_dir: str | Path, requirements_content: str = "") -> SecurityScanResult:
        """完整审计：静态扫描 + 依赖漏洞检查"""
        result = self.scan_source(source_dir)
        if requirements_content:
            result.dependency_vulnerabilities = self.audit_dependencies(requirements_content)

            high_dep_vulns = [
                v for v in result.dependency_vulnerabilities
                if v.severity == Severity.HIGH.value
            ]
            if high_dep_vulns and result.status != ScanStatus.REJECTED:
                result.status = ScanStatus.REJECTED
                for v in high_dep_vulns:
                    result.issues.append(SecurityIssue(
                        severity=Severity.HIGH, file="requirements.txt", line=0,
                        code="DEP001", message=f"{v.package}: {v.cve} — {v.description}",
                    ))

        return result

    def _parse_requirements(self, content: str) -> list[tuple[str, str]]:
        packages = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            match = re.match(r'^([a-zA-Z0-9_\-\.]+)\s*([><=~!]+.*)?$', line)
            if match:
                pkg = match.group(1).lower()
                ver = (match.group(2) or "").strip()
                packages.append((pkg, ver))
        return packages

security_scanner = SecurityScanner()
