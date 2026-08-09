"""Submission package contract for Dockerfile-first Agent projects."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from app.core.exceptions import ValidationException


MANIFEST_NAMES = ("agent-eval.yaml", "agent-eval.yml")
_SAFE_PATH = re.compile(r"^[A-Za-z0-9._/\-]+$")
_DOMAIN = re.compile(r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_PRIVATE_KEY = re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
_FORBIDDEN_SECRET_FILES = {".env", "id_rsa", "id_ed25519", "credentials.json"}


@dataclass(frozen=True)
class BuildContract:
    mode: str
    dockerfile: str
    context: str = "."


@dataclass(frozen=True)
class RuntimeContract:
    protocol: str = "stdio"
    port: int | None = None
    healthcheck: str = "/health"
    invoke: str = "/invoke"
    timeout_seconds: int = 300
    command: list[str] | None = None


@dataclass(frozen=True)
class SecurityContract:
    network: str = "none"
    allowed_domains: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AgentPackageContract:
    schema_version: int
    build: BuildContract
    runtime: RuntimeContract
    security: SecurityContract
    manifest_path: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "build": {"mode": self.build.mode, "dockerfile": self.build.dockerfile, "context": self.build.context},
            "runtime": {
                "protocol": self.runtime.protocol,
                "port": self.runtime.port,
                "healthcheck": self.runtime.healthcheck,
                "invoke": self.runtime.invoke,
                "timeout_seconds": self.runtime.timeout_seconds,
                "command": self.runtime.command,
            },
            "security": {"network": self.security.network, "allowed_domains": list(self.security.allowed_domains)},
            "manifest_path": self.manifest_path,
        }


def load_package_contract(root: Path, requested_dockerfile: str | None = None) -> AgentPackageContract:
    """Load a manifest or derive a safe legacy contract.

    The archive remains the source of truth. A user Dockerfile is preferred;
    legacy ``agent.py`` projects receive a generated Dockerfile later.
    """
    manifest = _find_at_project_root(root, MANIFEST_NAMES)
    data: dict[str, Any] = {}
    if manifest:
        if manifest.stat().st_size > 256 * 1024:
            raise ValidationException("agent-eval.yaml 超过 256KB 限制")
        try:
            loaded = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise ValidationException(f"agent-eval.yaml 无法解析: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ValidationException("agent-eval.yaml 顶层必须是对象")
        data = loaded

    if int(data.get("schema_version", 1)) != 1:
        raise ValidationException("仅支持 agent-eval.yaml schema_version: 1")

    build_data = _mapping(data.get("build"), "build")
    dockerfile = requested_dockerfile or build_data.get("dockerfile") or "Dockerfile"
    context = build_data.get("context", ".")
    _validate_relative_path(dockerfile, "Dockerfile")
    _validate_relative_path(context, "构建上下文")

    project_root = manifest.parent if manifest else _detect_project_root(root)
    dockerfile_path = (project_root / dockerfile).resolve()
    _ensure_within(project_root, dockerfile_path)
    context_path = (project_root / context).resolve()
    _ensure_within(project_root, context_path)
    if not context_path.is_dir():
        raise ValidationException("Docker 构建上下文不存在")
    if dockerfile_path != context_path and context_path not in dockerfile_path.parents:
        raise ValidationException("Dockerfile 必须位于 build.context 内")
    mode = "dockerfile" if dockerfile_path.is_file() else "legacy"
    if mode == "legacy" and not (project_root / "agent.py").is_file():
        raise ValidationException("源码包必须包含 Dockerfile；旧版兼容包则必须在项目根目录包含 agent.py")

    runtime_data = _mapping(data.get("runtime"), "runtime")
    protocol = str(runtime_data.get("protocol", "stdio")).lower()
    if protocol not in {"stdio", "http"}:
        raise ValidationException("runtime.protocol 仅支持 stdio 或 http")
    port = runtime_data.get("port")
    if protocol == "http":
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValidationException("HTTP 协议必须声明 1-65535 范围内的 runtime.port")
    timeout = int(runtime_data.get("timeout_seconds", 300))
    if not 1 <= timeout <= 3600:
        raise ValidationException("runtime.timeout_seconds 必须在 1-3600 之间")
    command = runtime_data.get("command")
    if command is not None and (
        not isinstance(command, list) or not command or len(command) > 64
        or not all(isinstance(x, str) and x and len(x) <= 4096 for x in command)
    ):
        raise ValidationException("runtime.command 必须是非空字符串数组")

    security_data = _mapping(data.get("security"), "security")
    network = str(security_data.get("network", "none")).lower()
    if network not in {"none", "restricted"}:
        raise ValidationException("security.network 仅支持 none 或 restricted")
    domains = security_data.get("allowed_domains", [])
    if not isinstance(domains, list) or not all(isinstance(x, str) and x for x in domains):
        raise ValidationException("security.allowed_domains 必须是域名字符串数组")
    if len(domains) > 100 or any(len(domain) > 253 or not _DOMAIN.fullmatch(domain) for domain in domains):
        raise ValidationException("security.allowed_domains 只能包含主机名，不能包含 URL、端口或通配符")
    if network == "none" and domains:
        raise ValidationException("network 为 none 时不能声明 allowed_domains")

    return AgentPackageContract(
        schema_version=1,
        build=BuildContract(mode=mode, dockerfile=dockerfile, context=context),
        runtime=RuntimeContract(
            protocol=protocol,
            port=port,
            healthcheck=_http_path(runtime_data.get("healthcheck", "/health")),
            invoke=_http_path(runtime_data.get("invoke", "/invoke")),
            timeout_seconds=timeout,
            command=command,
        ),
        security=SecurityContract(network=network, allowed_domains=tuple(domains)),
        manifest_path=manifest.relative_to(root).as_posix() if manifest else None,
    )


def reject_packaged_secrets(root: Path) -> None:
    """Reject common credential artifacts before they enter a build context."""
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.name.lower() in _FORBIDDEN_SECRET_FILES or path.suffix.lower() == ".key":
            raise ValidationException(f"源码包不能包含凭据文件: {path.relative_to(root)}")
        if path.stat().st_size <= 1024 * 1024:
            try:
                content = path.read_bytes()
            except OSError:
                continue
            if _PRIVATE_KEY.search(content):
                raise ValidationException(f"源码包不能包含私钥: {path.relative_to(root)}")


def resolve_project_root(root: Path, contract: AgentPackageContract) -> Path:
    if contract.manifest_path:
        return (root / contract.manifest_path).parent
    return _detect_project_root(root)


def contract_from_dict(data: dict[str, Any]) -> AgentPackageContract:
    """Rehydrate a previously validated contract from durable metadata."""
    build = data["build"]
    runtime = data["runtime"]
    security = data["security"]
    return AgentPackageContract(
        schema_version=int(data["schema_version"]),
        build=BuildContract(mode=build["mode"], dockerfile=build["dockerfile"], context=build.get("context", ".")),
        runtime=RuntimeContract(
            protocol=runtime["protocol"], port=runtime.get("port"), healthcheck=runtime.get("healthcheck", "/health"),
            invoke=runtime.get("invoke", "/invoke"), timeout_seconds=int(runtime.get("timeout_seconds", 300)), command=runtime.get("command"),
        ),
        security=SecurityContract(network=security.get("network", "none"), allowed_domains=tuple(security.get("allowed_domains", []))),
        manifest_path=data.get("manifest_path"),
    )


def _detect_project_root(root: Path) -> Path:
    children = [item for item in root.iterdir() if item.name not in {"__MACOSX"}]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return root


def _find_at_project_root(root: Path, names: tuple[str, ...]) -> Path | None:
    project_root = _detect_project_root(root)
    for name in names:
        candidate = project_root / name
        if candidate.is_file():
            return candidate
    return None


def _mapping(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValidationException(f"{field_name} 必须是对象")
    return value


def _validate_relative_path(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value or len(value) > 500 or not _SAFE_PATH.fullmatch(value):
        raise ValidationException(f"{label} 路径不合法")
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        raise ValidationException(f"{label} 必须位于项目目录内")


def _ensure_within(root: Path, target: Path) -> None:
    resolved = root.resolve()
    if target != resolved and resolved not in target.parents:
        raise ValidationException("构建路径越出项目目录")


def _http_path(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 2048 or not value.startswith("/") or "//" in value:
        raise ValidationException("HTTP 路径必须以 / 开头")
    return value
