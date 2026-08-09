import io
import logging
import tempfile
import tarfile
import zipfile
from dataclasses import replace
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
from app.services.agent_package import AgentPackageContract, SecurityContract, compile_uploaded_contract, load_package_contract, reject_packaged_secrets, resolve_project_root
from app.services.image_builder import validate_dockerfile
from app.schemas.request.intake import RuntimeConfigUpload, SubmissionMetadata
from app.services.capability_service import ParsedCatalog, parse_interface_spec

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    submission: Submission
    matched_tools: list[BuiltinTool] = field(default_factory=list)
    connectivity_result: ConnectivityResult | None = None
    scan_result: SecurityScanResult | None = None
    risk_assessment: RiskAssessment | None = None
    package_contract: AgentPackageContract | None = None
    capability_catalog: ParsedCatalog | None = None


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

        # 2. 解包并先完成所有本地契约与安全检查，避免为非法包调用外部模型端点。
        extract_dir = _extract_package(package_bytes, filename)
        try:
            reject_packaged_secrets(extract_dir)
            package_contract = load_package_contract(extract_dir, config.dockerfile_path)
            declared_domains = tuple(sorted(set(package_contract.security.allowed_domains) | set(config.allowed_domains)))
            if declared_domains:
                config.allowed_domains = list(declared_domains)
                package_contract = replace(
                    package_contract,
                    security=SecurityContract(network="restricted", allowed_domains=declared_domains),
                )
            if package_contract.build.mode == "dockerfile":
                project_root = resolve_project_root(extract_dir, package_contract)
                validate_dockerfile(project_root / package_contract.build.context / package_contract.build.dockerfile)
            elif package_contract.build.mode == "compose":
                project_root = resolve_project_root(extract_dir, package_contract)
                for service in package_contract.deployment.services:
                    if service.dockerfile:
                        validate_dockerfile(project_root / str(service.context or ".") / service.dockerfile)
            requirements_txt = _read_requirements(extract_dir)
            scan_result = security_scanner.full_audit(extract_dir, requirements_txt)

            if scan_result.status == ScanStatus.REJECTED:
                high_issues = [i for i in scan_result.issues if i.severity.value == "high"]
                detail = "; ".join(f"[{i.code}] {i.message}" for i in high_issues[:3])
                raise ValidationException(f"安全扫描不通过: {detail}")
        finally:
            _cleanup_dir(extract_dir)

        # 3. 模型连通性校验
        connectivity = await connectivity_checker.check(
            provider=config.llm_provider,
            api_base=config.llm_api_base,
            api_key=config.llm_api_key,
            model=config.llm_model,
        )
        if not connectivity.ok:
            raise ValidationException(f"模型连通性校验失败: {connectivity.error}")

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
        submission_status = "build_queued"

        # 9. 创建 Submission 记录 (先不写 DB，由 API 层处理)
        submission = Submission(
            agent_name=config.agent_name,
            version=config.version,
            agent_type=config.agent_type or "short_horizon",
            horizon="short" if config.agent_type != "long_horizon" else "long",
            subtype=config.subtype,
            risk_level=risk.level.value,
            # Credentials are runtime-only secrets.  Persisting the request model
            # verbatim would leak llm_api_key into the submissions JSONB column.
            config={**config.model_dump(exclude={"llm_api_key"}), "package_contract": package_contract.as_dict()},
            source_package_path="",
            source_package_hash="",
            status=submission_status,
            build_mode=package_contract.build.mode,
            deployment_type=package_contract.deployment.type,
            compose_file=package_contract.deployment.compose_file,
            entry_service=package_contract.deployment.entry_service,
            dockerfile_path=package_contract.build.dockerfile or package_contract.deployment.compose_file,
            runtime_protocol=package_contract.runtime.protocol,
            build_status="queued",
        )

        return PipelineResult(
            submission=submission,
            matched_tools=matched_tools,
            connectivity_result=connectivity,
            scan_result=scan_result,
            risk_assessment=risk,
            package_contract=package_contract,
        )

    async def run_verified_pipeline(
        self,
        metadata: SubmissionMetadata,
        runtime_config: RuntimeConfigUpload,
        package_bytes: bytes,
        package_filename: str,
        compose_bytes: bytes,
        interface_spec_bytes: bytes,
        interface_spec_filename: str,
    ) -> PipelineResult:
        """Validate the four explicit submission artifacts without user Manifest.

        This is the canonical intake path. It performs all deterministic checks
        before any durable object is created or asynchronous build is queued.
        """
        validate_and_extract(package_bytes, package_filename)
        catalog = parse_interface_spec(interface_spec_bytes, interface_spec_filename)
        extract_dir = _extract_package(package_bytes, package_filename)
        try:
            reject_packaged_secrets(extract_dir)
            contract = compile_uploaded_contract(extract_dir, compose_bytes, runtime_config)
            project_root = resolve_project_root(extract_dir, contract)
            for service in contract.deployment.services:
                if service.dockerfile:
                    validate_dockerfile(project_root / str(service.context or ".") / service.dockerfile)
            requirements_txt = _read_requirements(extract_dir)
            scan_result = security_scanner.full_audit(extract_dir, requirements_txt)
            if scan_result.status == ScanStatus.REJECTED:
                high_issues = [issue for issue in scan_result.issues if issue.severity.value == "high"]
                detail = "; ".join(f"[{issue.code}] {issue.message}" for issue in high_issues[:3])
                raise ValidationException(f"安全扫描不通过: {detail}")
        finally:
            _cleanup_dir(extract_dir)

        matched_tools = match_enabled_tools(metadata.enabled_tools)
        risk = assess_risk_level(matched_tools, scan_result, metadata.agent_type)
        config = {
            **metadata.model_dump(),
            "runtime_config": runtime_config.model_dump(mode="json"),
            "package_contract": contract.as_dict(),
        }
        submission = Submission(
            agent_name=metadata.agent_name,
            version=metadata.version,
            agent_type=metadata.agent_type,
            horizon="long" if metadata.agent_type == "long_horizon" else "short",
            subtype=metadata.subtype,
            risk_level=risk.level.value,
            config=config,
            source_package_path="",
            source_package_hash="",
            status="build_queued",
            build_mode="compose",
            deployment_type="compose",
            compose_file="uploaded:docker-compose.yaml",
            entry_service=contract.deployment.entry_service,
            dockerfile_path=None,
            runtime_protocol=contract.runtime.protocol,
            build_status="queued",
        )
        return PipelineResult(
            submission=submission,
            matched_tools=matched_tools,
            scan_result=scan_result,
            risk_assessment=risk,
            package_contract=contract,
            capability_catalog=catalog,
        )


def _extract_package(package_data: bytes, filename: str) -> Path:
    extract_dir = Path(tempfile.mkdtemp(prefix="agent_scan_"))
    try:
        if filename.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(package_data)) as zf:
                _safe_extract_zip(zf, extract_dir)
        else:
            with tarfile.open(fileobj=io.BytesIO(package_data), mode="r:gz") as tf:
                _safe_extract_tar(tf, extract_dir)
    except Exception:
        _cleanup_dir(extract_dir)
        raise ValidationException("无法解压源码包到临时目录")
    return extract_dir


def _validated_destination(root: Path, member_name: str) -> Path:
    """Return a safe extraction destination or reject archive traversal."""
    normalized = member_name.replace("\\", "/")
    if not normalized or normalized.startswith("/"):
        raise ValidationException(f"压缩包包含非法路径: {member_name}")
    destination = (root / normalized).resolve()
    root_resolved = root.resolve()
    if destination != root_resolved and root_resolved not in destination.parents:
        raise ValidationException(f"压缩包路径越界: {member_name}")
    return destination


def _safe_extract_zip(archive: zipfile.ZipFile, root: Path) -> None:
    for member in archive.infolist():
        destination = _validated_destination(root, member.filename)
        # Unix symlinks are encoded in the high file mode bits.
        if (member.external_attr >> 16) & 0o170000 == 0o120000:
            raise ValidationException(f"压缩包不允许符号链接: {member.filename}")
        if member.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source, destination.open("wb") as target:
            _copy_limited(source, target)


def _safe_extract_tar(archive: tarfile.TarFile, root: Path) -> None:
    for member in archive.getmembers():
        destination = _validated_destination(root, member.name)
        if member.issym() or member.islnk() or member.isdev() or member.isfifo():
            raise ValidationException(f"压缩包不允许特殊文件: {member.name}")
        if member.isdir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        if not member.isfile():
            continue
        source = archive.extractfile(member)
        if source is None:
            raise ValidationException(f"无法读取压缩包成员: {member.name}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with source, destination.open("wb") as target:
            _copy_limited(source, target)


def _copy_limited(source, target) -> None:
    """Copy one member while enforcing the package-wide configured size bound."""
    from app.infrastructure.minio import MAX_PACKAGE_SIZE

    copied = 0
    while chunk := source.read(1024 * 1024):
        copied += len(chunk)
        if copied > MAX_PACKAGE_SIZE:
            raise ValidationException("压缩包成员解压后超过大小限制")
        target.write(chunk)


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
