import io
import json
import logging
import tempfile
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from app.core.exceptions import ValidationException
from app.engine.builtin_tools import BuiltinTool, match_enabled_tools
from app.infrastructure.minio import validate_and_extract
from app.models.submission import Submission
from app.schemas.request.submission import SubmissionConfigRequest
from app.services.agent_type_identifier import agent_type_identifier
from app.services.config_generator import config_generator
from app.services.model_connectivity import ConnectivityResult, connectivity_checker
from app.services.risk_analyzer import RiskAssessment, assess_risk_level
from app.services.security_service import SecurityScanResult, security_scanner, ScanStatus

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    submission: Submission
    matched_tools: list[BuiltinTool] = field(default_factory=list)
    connectivity_result: ConnectivityResult | None = None
    scan_result: SecurityScanResult | None = None
    risk_assessment: RiskAssessment | None = None


class SubmissionService:
    """接入层完整流水线编排

    串联: 解包校验 → 模型连通性 → 安全扫描 → AI类型识别 → YAML生成 → 风险定级 → 存储
    """

    async def run_pipeline(
        self,
        config: SubmissionConfigRequest,
        package_bytes: bytes,
        filename: str,
    ) -> PipelineResult:
        # 1. 解包校验源码结构
        validate_and_extract(package_bytes, filename)

        # 2. 模型连通性校验
        connectivity = await connectivity_checker.check(
            provider=config.llm_provider,
            api_base=config.llm_api_base,
            api_key=config.llm_api_key,
            model=config.llm_model,
        )
        if not connectivity.ok:
            raise ValidationException(f"模型连通性校验失败: {connectivity.error}")

        # 3. 解包到临时目录，执行安全扫描 + 依赖审计
        extract_dir = _extract_package(package_bytes, filename)
        try:
            requirements_txt = _read_requirements(extract_dir)
            scan_result = security_scanner.full_audit(extract_dir, requirements_txt)

            if scan_result.status == ScanStatus.REJECTED:
                high_issues = [i for i in scan_result.issues if i.severity.value == "high"]
                detail = "; ".join(f"[{i.code}] {i.message}" for i in high_issues[:3])
                raise ValidationException(f"安全扫描不通过: {detail}")
        finally:
            _cleanup_dir(extract_dir)

        # 4. 工具匹配
        matched_tools = match_enabled_tools(config.enabled_tools)

        # 5. AI 类型识别
        if not config.agent_type or not config.subtype:
            identification = await agent_type_identifier.identify(config.description)
            if not config.agent_type:
                config.agent_type = identification.agent_type
            if not config.subtype:
                config.subtype = identification.subtype

        # 6. 生成 agent.config.yaml
        yaml_content = config_generator.generate(config)

        # 7. 风险定级
        risk = assess_risk_level(
            enabled_tools=matched_tools,
            security_result=scan_result,
            agent_type=config.agent_type or "",
        )

        # 8. 确定 submission 状态
        if scan_result.status == ScanStatus.VALIDATED_WITH_WARNINGS:
            submission_status = "validated_with_warnings"
        else:
            submission_status = "validated"

        # 9. 创建 Submission 记录 (先不写 DB，由 API 层处理)
        submission = Submission(
            agent_name=config.agent_name,
            version=config.version,
            agent_type=config.agent_type or "short_horizon",
            horizon="short" if config.agent_type != "long_horizon" else "long",
            subtype=config.subtype,
            risk_level=risk.level.value,
            config=config.model_dump(),
            source_package_path="",
            source_package_hash="",
            status=submission_status,
        )

        return PipelineResult(
            submission=submission,
            matched_tools=matched_tools,
            connectivity_result=connectivity,
            scan_result=scan_result,
            risk_assessment=risk,
        )


def _extract_package(package_data: bytes, filename: str) -> Path:
    extract_dir = Path(tempfile.mkdtemp(prefix="agent_scan_"))
    try:
        if filename.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(package_data)) as zf:
                zf.extractall(extract_dir)
        else:
            with tarfile.open(fileobj=io.BytesIO(package_data), mode="r:gz") as tf:
                tf.extractall(extract_dir)
    except Exception:
        _cleanup_dir(extract_dir)
        raise ValidationException("无法解压源码包到临时目录")
    return extract_dir


def _read_requirements(extract_dir: Path) -> str:
    for req_file in extract_dir.rglob("requirements.txt"):
        try:
            return req_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass
    return ""


def _cleanup_dir(path: Path):
    import shutil
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


submission_service = SubmissionService()
