"""Policy-controlled image building for untrusted Agent packages."""

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
    (re.compile(r"^\s*FROM\s+[^\s]+\s+AS\s+.*\bFROM\s+", re.I), "同一行多阶段 FROM"),
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


class ImageBuildError(RuntimeError):
    def __init__(self, message: str, build_log: str = ""):
        super().__init__(message)
        self.build_log = build_log


class ImageBuilder:
    """Build through a separately configured Docker-compatible builder.

    Production must point ``AGENT_BUILDER_DOCKER_HOST`` at a dedicated rootless
    builder. Falling back to the runtime daemon is allowed only in development.
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

    async def build(
        self,
        submission_id: str,
        source_root: Path,
        contract: AgentPackageContract,
        source_hash: str,
    ) -> ImageBuildResult:
        project_root = resolve_project_root(source_root, contract)
        dockerfile = project_root / contract.build.dockerfile
        if contract.build.mode == "legacy":
            dockerfile = project_root / ".agenteval.Dockerfile"
            (project_root / ".agenteval_legacy_stdio.py").write_text(_legacy_stdio_adapter(), encoding="utf-8")
            dockerfile.write_text(_legacy_dockerfile(), encoding="utf-8")
        validate_dockerfile(dockerfile)
        context = (project_root / contract.build.context).resolve()
        if not context.is_dir() or (context != project_root.resolve() and project_root.resolve() not in context.parents):
            raise ValidationException("Docker 构建上下文不存在或越出项目目录")
        build_fingerprint = hashlib.sha256(
            f"{source_hash}:{json.dumps(contract.as_dict(), sort_keys=True, separators=(',', ':'))}".encode()
        ).hexdigest()
        tag = f"{settings.AGENT_IMAGE_REPOSITORY}:{build_fingerprint[:24]}"

        def do_build() -> ImageBuildResult:
            image, logs = self.client.images.build(
                path=str(context),
                dockerfile=str(dockerfile.relative_to(context)),
                tag=tag,
                rm=True,
                forcerm=True,
                pull=settings.AGENT_BUILD_PULL_BASE_IMAGES,
                network_mode=settings.AGENT_BUILD_NETWORK_MODE,
                labels={"agenteval.submission_id": submission_id, "agenteval.source_sha256": source_hash, "agenteval.build_fingerprint": build_fingerprint},
            )
            text = "".join(item.get("stream", item.get("error", "")) for item in logs)
            image.reload()
            digest = _image_digest(image)
            security = inspect_and_scan_image(self.client, tag)
            published_ref = tag
            if settings.AGENT_IMAGE_PUSH:
                repository, image_tag = tag.rsplit(":", 1)
                auth_config = None
                if settings.AGENT_REGISTRY_USERNAME and settings.AGENT_REGISTRY_PASSWORD:
                    auth_config = {"username": settings.AGENT_REGISTRY_USERNAME, "password": settings.AGENT_REGISTRY_PASSWORD}
                push_events = self.client.images.push(repository, tag=image_tag, stream=True, decode=True, auth_config=auth_config)
                for event in push_events:
                    if event.get("error"):
                        raise RuntimeError(f"镜像推送失败: {event['error']}")
                    aux_digest = (event.get("aux") or {}).get("Digest", "")
                    if aux_digest.startswith("sha256:"):
                        digest = aux_digest.removeprefix("sha256:")
                published_ref = f"{repository}@sha256:{digest}"
            return ImageBuildResult(published_ref, image.id, digest, text[-settings.AGENT_BUILD_LOG_MAX_CHARS :], security.report, security.sbom)

        try:
            return await asyncio.wait_for(asyncio.to_thread(do_build), timeout=settings.AGENT_BUILD_TIMEOUT_SECONDS)
        except asyncio.TimeoutError as exc:
            raise TimeoutError(f"镜像构建超过 {settings.AGENT_BUILD_TIMEOUT_SECONDS} 秒") from exc
        except Exception as exc:
            events = getattr(exc, "build_log", None) or []
            log = "".join(item.get("stream", item.get("error", "")) for item in events if isinstance(item, dict))
            raise ImageBuildError(str(exc), log[-settings.AGENT_BUILD_LOG_MAX_CHARS :]) from exc
        finally:
            if settings.AGENT_IMAGE_PUSH:
                try:
                    await asyncio.to_thread(self.client.images.remove, tag, force=True)
                except Exception:
                    pass


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


def _legacy_dockerfile() -> str:
    return """FROM agenteval/sandbox:readonly\nCOPY . /agent\nUSER sandbox\nENTRYPOINT [\"python\", \"/agent/.agenteval_legacy_stdio.py\"]\n"""


def _legacy_stdio_adapter() -> str:
    return '''import json\nimport subprocess\nimport sys\nfrom pathlib import Path\n\ntask = json.load(sys.stdin)\nPath("/tmp/task.json").write_text(json.dumps(task), encoding="utf-8")\ncompleted = subprocess.run(["python", "/sandbox/agent_runner.py", "--task-file", "/tmp/task.json", "--output", "/tmp/result.json", "--trace-output", "/tmp/trace.json"], check=False)\nresult = json.loads(Path("/tmp/result.json").read_text(encoding="utf-8"))\ntrace = json.loads(Path("/tmp/trace.json").read_text(encoding="utf-8"))\nprint(json.dumps({"result": result, "trace": trace}, ensure_ascii=False))\nraise SystemExit(completed.returncode)\n'''


def _image_digest(image: Any) -> str:
    digests = image.attrs.get("RepoDigests") or []
    if digests and "@sha256:" in digests[0]:
        return digests[0].split("@sha256:", 1)[1]
    raw = str(image.id).removeprefix("sha256:")
    return raw if len(raw) == 64 else hashlib.sha256(raw.encode()).hexdigest()


image_builder: ImageBuilder | None = None


def get_image_builder() -> ImageBuilder:
    global image_builder
    if image_builder is None:
        image_builder = ImageBuilder()
    return image_builder
