"""Policy-controlled image builds for single-image and Compose deployments."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.exceptions import ValidationException
from app.services.agent_package import AgentPackageContract, resolve_project_root
from app.services.image_security import inspect_and_scan_image


_FORBIDDEN_DOCKERFILE = (
    (re.compile(r"^\s*ADD\b.*https?://", re.I), "远程 ADD"),
    (re.compile(r"^\s*(RUN|CMD|ENTRYPOINT).*--privileged", re.I), "特权参数"),
    (re.compile(r"/var/run/docker\.sock", re.I), "Docker Socket"),
)


@dataclass(frozen=True)
class ImageBuildResult:
    image_ref: str
    image_id: str
    image_digest: str
    build_log: str
    scan_report: dict[str, Any]
    sbom: dict[str, Any]
    service_images: dict[str, str]


class ImageBuildError(RuntimeError):
    def __init__(self, message: str, build_log: str = ""):
        super().__init__(message)
        self.build_log = build_log


class ImageBuilder:
    """Build local services on the isolated builder daemon.

    External Compose images are retained by immutable user declaration. Local
    build services are built, scanned and optionally pushed independently.
    """

    def __init__(self, client: Any | None = None):
        if client is None:
            try:
                import docker
            except ImportError as exc:
                raise RuntimeError("Docker SDK is not installed") from exc
            if settings.AGENT_BUILDER_DOCKER_HOST:
                client = docker.DockerClient(base_url=settings.AGENT_BUILDER_DOCKER_HOST)
            elif settings.ENVIRONMENT.lower() == "production":
                raise RuntimeError("生产环境必须配置独立的 AGENT_BUILDER_DOCKER_HOST")
            else:
                client = docker.from_env()
        self.client = client

    async def build(self, submission_id: str, source_root: Path, contract: AgentPackageContract, source_hash: str) -> ImageBuildResult:
        project_root = resolve_project_root(source_root, contract)
        fingerprint = hashlib.sha256(
            f"{source_hash}:{json.dumps(contract.as_dict(), sort_keys=True, separators=(',', ':'))}".encode()
        ).hexdigest()

        def do_build() -> ImageBuildResult:
            if contract.deployment.type == "compose":
                specs = [(s.name, s.context, s.dockerfile, s.image, {target for _, target in s.volumes}) for s in contract.deployment.services]
            else:
                specs = [(contract.deployment.entry_service, contract.build.context, contract.build.dockerfile, None, set())]
            service_images: dict[str, str] = {}
            reports: dict[str, Any] = {}
            sboms: dict[str, Any] = {}
            log_parts: list[str] = []
            entry_id = ""
            entry_digest = ""
            for index, (name, context_name, dockerfile_name, external_image, allowed_volumes) in enumerate(specs):
                if external_image and not dockerfile_name:
                    try:
                        image = self.client.images.get(external_image)
                    except Exception:
                        image = self.client.images.pull(external_image)
                    image.reload()
                    immutable = _immutable_ref(external_image, image)
                    security = inspect_and_scan_image(self.client, immutable, allowed_volumes)
                    service_images[name] = immutable
                    reports[name] = security.report
                    sboms[name] = security.sbom
                    log_parts.append(f"\n===== external service: {name} ({immutable}) =====\n")
                    continue
                context = (project_root / str(context_name or ".")).resolve()
                dockerfile = context / str(dockerfile_name or "Dockerfile")
                validate_dockerfile(dockerfile)
                tag = f"{settings.AGENT_IMAGE_REPOSITORY}:{fingerprint[:16]}-{index}-{name}"
                image, logs = self.client.images.build(
                    path=str(context), dockerfile=str(dockerfile.relative_to(context)), tag=tag,
                    rm=True, forcerm=True, pull=settings.AGENT_BUILD_PULL_BASE_IMAGES,
                    network_mode=settings.AGENT_BUILD_NETWORK_MODE,
                    labels={"agenteval.submission_id": submission_id, "agenteval.service": name,
                            "agenteval.source_sha256": source_hash, "agenteval.build_fingerprint": fingerprint},
                )
                log_parts.append(f"\n===== service: {name} =====\n")
                log_parts.extend(event.get("stream", event.get("error", "")) for event in logs)
                image.reload()
                digest = _image_digest(image)
                security = inspect_and_scan_image(self.client, tag, allowed_volumes)
                published = self._publish(tag, digest) if settings.AGENT_IMAGE_PUSH else tag
                service_images[name] = published
                reports[name] = security.report
                sboms[name] = security.sbom
                if name == contract.deployment.entry_service:
                    entry_id, entry_digest = image.id, digest
            entry_ref = service_images.get(contract.deployment.entry_service)
            if not entry_ref:
                raise RuntimeError("入口服务没有可运行镜像")
            if not entry_digest:
                entry_digest = hashlib.sha256(entry_ref.encode()).hexdigest()
                entry_id = entry_ref
            return ImageBuildResult(
                entry_ref, entry_id, entry_digest,
                "".join(log_parts)[-settings.AGENT_BUILD_LOG_MAX_CHARS:], reports, sboms, service_images,
            )

        try:
            return await asyncio.wait_for(asyncio.to_thread(do_build), timeout=settings.AGENT_BUILD_TIMEOUT_SECONDS)
        except asyncio.TimeoutError as exc:
            raise TimeoutError(f"镜像构建超过 {settings.AGENT_BUILD_TIMEOUT_SECONDS} 秒") from exc
        except Exception as exc:
            events = getattr(exc, "build_log", None) or []
            log = "".join(item.get("stream", item.get("error", "")) for item in events if isinstance(item, dict))
            raise ImageBuildError(str(exc), log[-settings.AGENT_BUILD_LOG_MAX_CHARS:]) from exc

    def _publish(self, tag: str, digest: str) -> str:
        repository, image_tag = tag.rsplit(":", 1)
        auth = None
        if settings.AGENT_REGISTRY_USERNAME and settings.AGENT_REGISTRY_PASSWORD:
            auth = {"username": settings.AGENT_REGISTRY_USERNAME, "password": settings.AGENT_REGISTRY_PASSWORD}
        for event in self.client.images.push(repository, tag=image_tag, stream=True, decode=True, auth_config=auth):
            if event.get("error"):
                raise RuntimeError(f"镜像推送失败: {event['error']}")
            pushed = (event.get("aux") or {}).get("Digest", "")
            if pushed.startswith("sha256:"):
                digest = pushed.removeprefix("sha256:")
        return f"{repository}@sha256:{digest}"


def validate_dockerfile(path: Path) -> None:
    if not path.is_file():
        raise ValidationException(f"Dockerfile 不存在: {path.name}")
    if path.stat().st_size > settings.AGENT_DOCKERFILE_MAX_BYTES:
        raise ValidationException("Dockerfile 超过大小限制")
    text = path.read_text(encoding="utf-8", errors="strict")
    instructions = [line for line in _logical_lines(text) if line and not line.lstrip().startswith("#")]
    if not instructions or not any(re.match(r"^\s*FROM\s+", line, re.I) for line in instructions):
        raise ValidationException("Dockerfile 必须包含 FROM 指令")
    for line in instructions:
        for pattern, reason in _FORBIDDEN_DOCKERFILE:
            if pattern.search(line):
                raise ValidationException(f"Dockerfile 包含禁止内容: {reason}")


def _logical_lines(text: str) -> list[str]:
    result: list[str] = []
    current = ""
    for raw in text.splitlines():
        current += raw.strip()
        if current.endswith("\\"):
            current = current[:-1] + " "
        else:
            result.append(current)
            current = ""
    if current:
        result.append(current)
    return result


def _image_digest(image: Any) -> str:
    digests = image.attrs.get("RepoDigests") or []
    if digests and "@sha256:" in digests[0]:
        return digests[0].split("@sha256:", 1)[1]
    raw = str(image.id).removeprefix("sha256:")
    return raw if len(raw) == 64 else hashlib.sha256(raw.encode()).hexdigest()


def _immutable_ref(requested: str, image: Any) -> str:
    if "@sha256:" in requested:
        return requested
    digests = image.attrs.get("RepoDigests") or []
    if digests:
        return str(digests[0])
    raise RuntimeError(f"外部镜像无法解析为不可变 digest: {requested}")


image_builder: ImageBuilder | None = None


def get_image_builder() -> ImageBuilder:
    global image_builder
    if image_builder is None:
        image_builder = ImageBuilder()
    return image_builder
