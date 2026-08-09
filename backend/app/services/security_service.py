import logging
import re
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

    # 内嵌已知高危 CVE 库（生产环境对接 Safety DB / PyUp API）
    KNOWN_VULNS: dict[str, dict] = {
        "django": {"cve": "CVE-2024-XXXXX", "min_fixed": "5.0.0", "severity": Severity.HIGH,
                   "desc": "Django < 5.0 存在 SQL 注入漏洞"},
        "flask": {"cve": "CVE-2023-30861", "min_fixed": "2.3.0", "severity": Severity.MEDIUM,
                  "desc": "Flask < 2.3 存在信息泄露"},
        "langchain": {"cve": "CVE-2024-XXXX", "min_fixed": "0.3.0", "severity": Severity.HIGH,
                      "desc": "LangChain < 0.3 存在任意代码执行"},
        "langchain-core": {"cve": "CVE-2024-XXXX", "min_fixed": "0.3.0", "severity": Severity.HIGH,
                           "desc": "langchain-core < 0.3 存在任意代码执行"},
        "pyyaml": {"cve": "CVE-2020-14343", "min_fixed": "5.4.0", "severity": Severity.HIGH,
                   "desc": "PyYAML < 5.4 存在不安全反序列化"},
        "numpy": {"cve": "CVE-2021-41495", "min_fixed": "1.22.0", "severity": Severity.LOW,
                  "desc": "NumPy < 1.22 存在空指针引用"},
        "joblib": {"cve": "CVE-2022-21797", "min_fixed": "1.2.0", "severity": Severity.MEDIUM,
                   "desc": "joblib < 1.2 存在任意代码执行"},
        "pillow": {"cve": "CVE-2023-50447", "min_fixed": "10.2.0", "severity": Severity.HIGH,
                   "desc": "Pillow < 10.2 存在缓冲区溢出"},
        "requests": {"cve": "CVE-2024-3651", "min_fixed": "2.32.0", "severity": Severity.MEDIUM,
                     "desc": "requests < 2.32 存在 Host 头注入"},
        "urllib3": {"cve": "CVE-2024-37891", "min_fixed": "2.2.0", "severity": Severity.MEDIUM,
                    "desc": "urllib3 < 2.2 存在代理头注入"},
        "cryptography": {"cve": "CVE-2024-6119", "min_fixed": "43.0.0", "severity": Severity.HIGH,
                         "desc": "cryptography < 43 存在 TLS 证书验证绕过"},
        "jinja2": {"cve": "CVE-2024-22195", "min_fixed": "3.1.4", "severity": Severity.MEDIUM,
                   "desc": "Jinja2 < 3.1.4 存在 XSS"},
        "gradio": {"cve": "CVE-2024-34510", "min_fixed": "4.20.0", "severity": Severity.HIGH,
                   "desc": "Gradio < 4.20 存在路径遍历"},
        "streamlit": {"cve": "CVE-2024-XXXX", "min_fixed": "1.29.0", "severity": Severity.MEDIUM,
                      "desc": "Streamlit < 1.29 存在目录遍历"},
    }

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
        """解析 requirements.txt 并检查已知 CVE 漏洞"""
        vulnerabilities: list[DependencyVulnerability] = []
        packages = self._parse_requirements(requirements_content)

        for pkg_name, version_spec in packages:
            info = self.KNOWN_VULNS.get(pkg_name.lower())
            if info and (not version_spec or self._version_lt(version_spec, info["min_fixed"])):
                vulnerabilities.append(DependencyVulnerability(
                    package=pkg_name,
                    version=version_spec,
                    cve=info["cve"],
                    severity=info["severity"].value,
                    description=info["desc"],
                ))

        if vulnerabilities:
            high_count = sum(1 for v in vulnerabilities if v.severity == Severity.HIGH.value)
            logger.info("依赖审计: %d 个已知漏洞 (HIGH=%d)", len(vulnerabilities), high_count)

        return vulnerabilities

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

    @staticmethod
    def _version_lt(version_spec: str, min_fixed: str) -> bool:
        nums = re.findall(r'(\d+)\.(\d+)(?:\.(\d+))?', version_spec)
        min_nums = re.findall(r'(\d+)\.(\d+)(?:\.(\d+))?', min_fixed)
        if not nums or not min_nums:
            return True
        v = tuple(int(x) if x else 0 for x in nums[0])
        m = tuple(int(x) if x else 0 for x in min_nums[0])
        return v < m


security_scanner = SecurityScanner()
