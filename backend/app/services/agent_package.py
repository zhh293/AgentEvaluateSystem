"""Validated deployment, invocation and evaluation contract for Agent projects.

The uploaded archive is immutable source material.  ``agent-eval.yaml`` is the
mandatory platform contract; Docker Compose describes a multi-service topology
and Dockerfile remains the lightweight single-service deployment option.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from app.core.exceptions import ValidationException


MANIFEST_NAMES = ("agent-eval.yaml", "agent-eval.yml")
COMPOSE_NAMES = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")
_SAFE_PATH = re.compile(r"^[A-Za-z0-9._/\-]+$")
_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}$")
_DOMAIN = re.compile(r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_PRIVATE_KEY = re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
_FORBIDDEN_SECRET_FILES = {".env", "id_rsa", "id_ed25519", "credentials.json"}
_FORBIDDEN_SERVICE_KEYS = {
    "privileged", "devices", "device_cgroup_rules", "network_mode", "pid", "ipc",
    "uts", "userns_mode", "cgroup", "cgroup_parent", "cap_add", "security_opt",
    "container_name", "ports", "expose", "extends", "volumes_from",
}


@dataclass(frozen=True)
class BuildContract:
    mode: str
    dockerfile: str | None = None
    context: str = "."


@dataclass(frozen=True)
class ComposeService:
    name: str
    image: str | None = None
    dockerfile: str | None = None
    context: str | None = None
    command: list[str] | None = None
    entrypoint: list[str] | None = None
    environment: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    depends_on: tuple[str, ...] = field(default_factory=tuple)
    volumes: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    healthcheck: tuple[str, ...] | None = None


@dataclass(frozen=True)
class DeploymentContract:
    type: str
    compose_file: str | None = None
    entry_service: str = "agent"
    services: tuple[ComposeService, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RuntimeContract:
    protocol: str = "http"
    port: int | None = None
    healthcheck: str = "/health"
    invoke: str = "/v1/evaluations/run"
    reset: str | None = None
    timeout_seconds: int = 300
    startup_timeout_seconds: int = 120
    command: list[str] | None = None
    state_scope: str = "evaluation"


@dataclass(frozen=True)
class SecurityContract:
    network: str = "none"
    allowed_domains: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AgentPackageContract:
    schema_version: int
    deployment: DeploymentContract
    build: BuildContract
    runtime: RuntimeContract
    security: SecurityContract
    manifest_path: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "deployment": {
                "type": self.deployment.type,
                "compose_file": self.deployment.compose_file,
                "entry_service": self.deployment.entry_service,
                "services": [
                    {
                        "name": s.name, "image": s.image, "dockerfile": s.dockerfile,
                        "context": s.context, "command": s.command, "entrypoint": s.entrypoint,
                        "environment": dict(s.environment), "depends_on": list(s.depends_on),
                        "volumes": [{"source": source, "target": target} for source, target in s.volumes],
                        "healthcheck": list(s.healthcheck) if s.healthcheck else None,
                    }
                    for s in self.deployment.services
                ],
            },
            "build": {"mode": self.build.mode, "dockerfile": self.build.dockerfile, "context": self.build.context},
            "runtime": {
                "protocol": self.runtime.protocol, "port": self.runtime.port,
                "healthcheck": self.runtime.healthcheck, "invoke": self.runtime.invoke,
                "reset": self.runtime.reset, "timeout_seconds": self.runtime.timeout_seconds,
                "startup_timeout_seconds": self.runtime.startup_timeout_seconds,
                "command": self.runtime.command, "state_scope": self.runtime.state_scope,
            },
            "security": {"network": self.security.network, "allowed_domains": list(self.security.allowed_domains)},
            "manifest_path": self.manifest_path,
        }


def load_package_contract(root: Path, requested_dockerfile: str | None = None) -> AgentPackageContract:
    manifest = _find_at_project_root(root, MANIFEST_NAMES)
    if not manifest:
        raise ValidationException("源码包根目录必须包含 agent-eval.yaml；平台不再猜测启动方式")
    if manifest.stat().st_size > 256 * 1024:
        raise ValidationException("agent-eval.yaml 超过 256KB 限制")
    try:
        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValidationException(f"agent-eval.yaml 无法解析: {exc}") from exc
    if not isinstance(data, dict) or int(data.get("schema_version", 0)) != 1:
        raise ValidationException("agent-eval.yaml 必须是对象并声明 schema_version: 1")

    project_root = manifest.parent
    deployment_data = _mapping(data.get("deployment"), "deployment")
    deployment_type = str(deployment_data.get("type", "")).lower()
    if deployment_type not in {"compose", "image"}:
        raise ValidationException("deployment.type 必须是 compose 或 image")
    entry_service = str(deployment_data.get("entry_service", "agent"))
    if not _NAME.fullmatch(entry_service):
        raise ValidationException("deployment.entry_service 不合法")

    services: tuple[ComposeService, ...] = ()
    compose_file: str | None = None
    build_data = _mapping(data.get("build"), "build")
    if deployment_type == "compose":
        compose_file = str(deployment_data.get("file") or _detect_compose_file(project_root) or "")
        _validate_relative_path(compose_file, "Compose 文件")
        compose_path = (project_root / compose_file).resolve()
        _ensure_within(project_root, compose_path)
        services = _load_compose(compose_path, project_root)
        if entry_service not in {service.name for service in services}:
            raise ValidationException("deployment.entry_service 必须引用 Compose 中存在的服务")
        build = BuildContract(mode="compose")
    else:
        dockerfile = requested_dockerfile or build_data.get("dockerfile") or "Dockerfile"
        context = build_data.get("context", ".")
        _validate_build_paths(project_root, dockerfile, context)
        build = BuildContract(mode="dockerfile", dockerfile=dockerfile, context=context)

    runtime_data = _mapping(data.get("runtime"), "runtime")
    protocol = str(runtime_data.get("protocol", "http")).lower()
    if protocol not in {"stdio", "http"}:
        raise ValidationException("runtime.protocol 仅支持 stdio 或 http")
    if deployment_type == "compose" and protocol == "stdio":
        raise ValidationException("Compose 多服务部署必须使用 HTTP 调用协议")
    port = runtime_data.get("port")
    if protocol == "http" and (not isinstance(port, int) or not 1 <= port <= 65535):
        raise ValidationException("HTTP 协议必须声明 1-65535 范围内的 runtime.port")
    timeout = _bounded_int(runtime_data.get("timeout_seconds", 300), 1, 3600, "runtime.timeout_seconds")
    startup_timeout = _bounded_int(runtime_data.get("startup_timeout_seconds", 120), 1, 600, "runtime.startup_timeout_seconds")
    command = _string_list(runtime_data.get("command"), "runtime.command", optional=True)
    state_scope = str(runtime_data.get("state_scope", "evaluation"))
    if state_scope not in {"case", "evaluation", "session"}:
        raise ValidationException("runtime.state_scope 仅支持 case、evaluation 或 session")

    security_data = _mapping(data.get("security"), "security")
    network = str(security_data.get("network", "none")).lower()
    if network not in {"none", "restricted"}:
        raise ValidationException("security.network 仅支持 none 或 restricted")
    domains = security_data.get("allowed_domains", [])
    if not isinstance(domains, list) or len(domains) > 100 or any(
        not isinstance(d, str) or len(d) > 253 or not _DOMAIN.fullmatch(d) for d in domains
    ):
        raise ValidationException("security.allowed_domains 只能包含合法主机名")
    if network == "none" and domains:
        raise ValidationException("network 为 none 时不能声明 allowed_domains")

    return AgentPackageContract(
        schema_version=1,
        deployment=DeploymentContract(deployment_type, compose_file, entry_service, services),
        build=build,
        runtime=RuntimeContract(
            protocol=protocol, port=port,
            healthcheck=_http_path(runtime_data.get("healthcheck", "/health")),
            invoke=_http_path(runtime_data.get("invoke", "/v1/evaluations/run")),
            reset=_optional_http_path(runtime_data.get("reset")), timeout_seconds=timeout,
            startup_timeout_seconds=startup_timeout, command=command, state_scope=state_scope,
        ),
        security=SecurityContract(network, tuple(sorted(set(domains)))),
        manifest_path=manifest.relative_to(root).as_posix(),
    )


def compile_uploaded_contract(
    root: Path,
    compose_content: bytes,
    runtime_config: Any,
) -> AgentPackageContract:
    """Compile untrusted uploaded topology/config into the internal contract.

    The temporary Compose file is only parsed by the platform. It is removed
    immediately and is never executed with Docker Compose.
    """
    if len(compose_content) > 512 * 1024:
        raise ValidationException("Docker Compose 文件超过 512KB 限制")
    project_root = _detect_project_root(root)
    temporary = project_root / ".agenteval-uploaded-compose.yaml"
    if temporary.exists():
        raise ValidationException("源码包包含平台保留文件 .agenteval-uploaded-compose.yaml")
    try:
        temporary.write_bytes(compose_content)
        services = _load_compose(temporary, project_root)
    finally:
        temporary.unlink(missing_ok=True)

    entry_service = runtime_config.entry_service
    if entry_service not in {service.name for service in services}:
        raise ValidationException("runtime config 的 entry_service 不存在于 Compose services")
    runtime = runtime_config.runtime
    protocol = "http" if runtime.protocol.value == "http" else "stdio"
    if protocol == "stdio" and len(services) != 1:
        raise ValidationException("CLI Agent 必须使用单服务 Compose；多服务调用统一使用 HTTP")
    security = runtime_config.network
    return AgentPackageContract(
        schema_version=1,
        deployment=DeploymentContract(
            type="compose",
            compose_file="uploaded:docker-compose.yaml",
            entry_service=entry_service,
            services=services,
        ),
        build=BuildContract(mode="compose"),
        runtime=RuntimeContract(
            protocol=protocol,
            port=runtime.port,
            healthcheck=runtime.healthcheck.path if runtime.healthcheck else "/health",
            invoke=runtime.invoke_path,
            reset=runtime.reset.path if runtime.reset else None,
            timeout_seconds=runtime.case_timeout_seconds,
            startup_timeout_seconds=runtime.startup_timeout_seconds,
            command=runtime.command,
            state_scope=runtime.state_scope,
        ),
        security=SecurityContract(
            network=security.mode,
            allowed_domains=tuple(security.allowed_domains),
        ),
        manifest_path="verified-manifest.json",
    )


def _load_compose(path: Path, project_root: Path) -> tuple[ComposeService, ...]:
    if not path.is_file() or path.stat().st_size > 512 * 1024:
        raise ValidationException("Compose 文件不存在或超过 512KB")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValidationException(f"Compose 文件无法解析: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("services"), dict) or not data["services"]:
        raise ValidationException("Compose 必须包含非空 services 对象")
    if len(data["services"]) > 6:
        raise ValidationException("单个 Agent 最多声明 6 个 Compose 服务")
    for forbidden in ("networks", "secrets", "configs", "include"):
        if forbidden in data:
            raise ValidationException(f"平台不接受 Compose 顶层 {forbidden}；运行资源由平台管理")
    declared_volumes = data.get("volumes", {})
    if not isinstance(declared_volumes, dict) or any(value not in (None, {}) for value in declared_volumes.values()):
        raise ValidationException("Compose 顶层 volumes 只能声明由平台接管的空命名卷")
    result: list[ComposeService] = []
    names = set(data["services"])
    for name, raw in data["services"].items():
        if not isinstance(name, str) or not _NAME.fullmatch(name) or not isinstance(raw, dict):
            raise ValidationException("Compose 服务名或定义不合法")
        bad = sorted(_FORBIDDEN_SERVICE_KEYS.intersection(raw))
        if bad:
            raise ValidationException(f"Compose 服务 {name} 包含平台禁止字段: {', '.join(bad)}")
        volumes = _named_volumes(raw.get("volumes"), declared_volumes, name)
        healthcheck = _healthcheck(raw.get("healthcheck"), name)
        image = raw.get("image")
        build_raw = raw.get("build")
        dockerfile = context = None
        if build_raw is not None:
            build_map = {"context": build_raw} if isinstance(build_raw, str) else _mapping(build_raw, f"services.{name}.build")
            allowed_build = {"context", "dockerfile"}
            unknown = set(build_map) - allowed_build
            if unknown:
                raise ValidationException(f"Compose 服务 {name} build 包含不支持字段: {', '.join(sorted(unknown))}")
            context = str(build_map.get("context", "."))
            dockerfile = str(build_map.get("dockerfile", "Dockerfile"))
            _validate_build_paths(project_root, dockerfile, context)
        if not image and not build_raw:
            raise ValidationException(f"Compose 服务 {name} 必须声明 image 或 build")
        if image is not None and (not isinstance(image, str) or not image or "${" in image or "@" not in image and ":" not in image):
            raise ValidationException(f"Compose 服务 {name} 的外部 image 必须显式固定 tag 或 digest")
        environment = _environment(raw.get("environment"), name)
        depends = raw.get("depends_on", [])
        depends_names = list(depends) if isinstance(depends, (list, dict)) else []
        if not all(isinstance(x, str) and x in names and x != name for x in depends_names):
            raise ValidationException(f"Compose 服务 {name} 的 depends_on 不合法")
        result.append(ComposeService(
            name=name, image=image, dockerfile=dockerfile, context=context,
            command=_string_list(raw.get("command"), f"services.{name}.command", optional=True),
            entrypoint=_string_list(raw.get("entrypoint"), f"services.{name}.entrypoint", optional=True),
            environment=tuple(sorted(environment.items())), depends_on=tuple(depends_names), volumes=volumes,
            healthcheck=healthcheck,
        ))
    _assert_acyclic(result)
    return tuple(result)


def reject_packaged_secrets(root: Path) -> None:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.name.lower() in _FORBIDDEN_SECRET_FILES or path.suffix.lower() == ".key":
            raise ValidationException(f"源码包不能包含凭据文件: {path.relative_to(root)}")
        if path.stat().st_size <= 1024 * 1024 and _PRIVATE_KEY.search(path.read_bytes()):
            raise ValidationException(f"源码包不能包含私钥: {path.relative_to(root)}")


def resolve_project_root(root: Path, contract: AgentPackageContract) -> Path:
    return (root / contract.manifest_path).parent


def contract_from_dict(data: dict[str, Any]) -> AgentPackageContract:
    deployment = data["deployment"]
    services = tuple(ComposeService(
        name=s["name"], image=s.get("image"), dockerfile=s.get("dockerfile"), context=s.get("context"),
        command=s.get("command"), entrypoint=s.get("entrypoint"),
        environment=tuple(sorted((s.get("environment") or {}).items())), depends_on=tuple(s.get("depends_on", [])),
        volumes=tuple((v["source"], v["target"]) for v in s.get("volumes", [])),
        healthcheck=tuple(s["healthcheck"]) if s.get("healthcheck") else None,
    ) for s in deployment.get("services", []))
    build, runtime, security = data["build"], data["runtime"], data["security"]
    return AgentPackageContract(
        int(data["schema_version"]),
        DeploymentContract(deployment["type"], deployment.get("compose_file"), deployment.get("entry_service", "agent"), services),
        BuildContract(build["mode"], build.get("dockerfile"), build.get("context", ".")),
        RuntimeContract(runtime["protocol"], runtime.get("port"), runtime.get("healthcheck", "/health"),
                        runtime.get("invoke", "/v1/evaluations/run"), runtime.get("reset"),
                        int(runtime.get("timeout_seconds", 300)), int(runtime.get("startup_timeout_seconds", 120)),
                        runtime.get("command"), runtime.get("state_scope", "evaluation")),
        SecurityContract(security.get("network", "none"), tuple(security.get("allowed_domains", []))),
        data["manifest_path"],
    )


def _detect_project_root(root: Path) -> Path:
    children = [item for item in root.iterdir() if item.name != "__MACOSX"]
    return children[0] if len(children) == 1 and children[0].is_dir() else root


def _find_at_project_root(root: Path, names: tuple[str, ...]) -> Path | None:
    project_root = _detect_project_root(root)
    return next((project_root / name for name in names if (project_root / name).is_file()), None)


def _detect_compose_file(root: Path) -> str | None:
    return next((name for name in COMPOSE_NAMES if (root / name).is_file()), None)


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValidationException(f"{name} 必须是对象")
    return value


def _validate_relative_path(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value or len(value) > 500 or not _SAFE_PATH.fullmatch(value):
        raise ValidationException(f"{label} 路径不合法")
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        raise ValidationException(f"{label} 必须位于项目目录内")


def _validate_build_paths(root: Path, dockerfile: str, context: str) -> None:
    _validate_relative_path(dockerfile, "Dockerfile")
    _validate_relative_path(context, "构建上下文")
    context_path = (root / context).resolve()
    dockerfile_path = (context_path / dockerfile).resolve()
    _ensure_within(root, context_path)
    _ensure_within(context_path, dockerfile_path)
    if not context_path.is_dir() or not dockerfile_path.is_file():
        raise ValidationException("Docker 构建上下文或 Dockerfile 不存在")


def _ensure_within(root: Path, target: Path) -> None:
    resolved = root.resolve()
    if target != resolved and resolved not in target.parents:
        raise ValidationException("路径越出项目目录")


def _string_list(value: Any, name: str, optional: bool = False) -> list[str] | None:
    if value is None and optional:
        return None
    if isinstance(value, str):
        raise ValidationException(f"{name} 必须使用字符串数组，禁止 shell 字符串")
    if not isinstance(value, list) or not value or len(value) > 64 or not all(isinstance(x, str) and x and len(x) <= 4096 for x in value):
        raise ValidationException(f"{name} 必须是非空字符串数组")
    return value


def _environment(value: Any, service: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict) or len(value) > 100:
        raise ValidationException(f"Compose 服务 {service} environment 必须是对象")
    result: dict[str, str] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or not _NAME.fullmatch(key) or raw is None or isinstance(raw, (dict, list)):
            raise ValidationException(f"Compose 服务 {service} environment 不合法")
        text = str(raw)
        if "${" in text or len(text) > 4096:
            raise ValidationException(f"Compose 服务 {service} 禁止环境变量插值或超长值")
        result[key] = text
    return result


def _named_volumes(value: Any, declared: dict[str, Any], service: str) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or len(value) > 8:
        raise ValidationException(f"Compose 服务 {service} volumes 必须是命名卷数组")
    result: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, str) or ":" not in item:
            raise ValidationException(f"Compose 服务 {service} 只允许 source:/absolute/target 格式的命名卷")
        source, target, *options = item.split(":")
        if source not in declared or not target.startswith("/") or ".." in PurePosixPath(target).parts:
            raise ValidationException(f"Compose 服务 {service} 禁止宿主路径或未声明卷")
        if options and options != ["rw"]:
            raise ValidationException(f"Compose 服务 {service} 命名卷只能使用 rw 模式")
        result.append((source, target))
    return tuple(result)


def _healthcheck(value: Any, service: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - {"test"}:
        raise ValidationException(f"Compose 服务 {service} healthcheck 只支持 test")
    test = value.get("test")
    if not isinstance(test, list) or len(test) < 2 or test[0] != "CMD" or not all(isinstance(x, str) and x for x in test):
        raise ValidationException(f"Compose 服务 {service} healthcheck 必须使用 CMD 数组，禁止 shell")
    return tuple(test[1:])


def _assert_acyclic(services: list[ComposeService]) -> None:
    graph = {service.name: service.depends_on for service in services}
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(name: str) -> None:
        if name in visiting:
            raise ValidationException("Compose depends_on 存在循环依赖")
        if name in visited:
            return
        visiting.add(name)
        for dependency in graph[name]:
            visit(dependency)
        visiting.remove(name)
        visited.add(name)
    for name in graph:
        visit(name)


def _bounded_int(value: Any, low: int, high: int, name: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationException(f"{name} 必须是整数") from exc
    if not low <= result <= high:
        raise ValidationException(f"{name} 必须在 {low}-{high} 之间")
    return result


def _http_path(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 2048 or not value.startswith("/") or "//" in value:
        raise ValidationException("HTTP 路径必须以 / 开头")
    return value


def _optional_http_path(value: Any) -> str | None:
    return None if value is None else _http_path(value)
