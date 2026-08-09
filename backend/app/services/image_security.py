"""Post-build image policy, vulnerability scan and SBOM generation."""

from __future__ import annotations

import json
import subprocess
import os
from dataclasses import dataclass
from typing import Any

from app.core.config import settings


@dataclass(frozen=True)
class ImageSecurityResult:
    report: dict[str, Any]
    sbom: dict[str, Any]


def inspect_and_scan_image(client: Any, image_ref: str) -> ImageSecurityResult:
    image = client.images.get(image_ref)
    image.reload()
    size = int(image.attrs.get("Size", 0))
    if size > settings.AGENT_IMAGE_MAX_BYTES:
        raise RuntimeError(f"镜像大小 {size} 超过限制 {settings.AGENT_IMAGE_MAX_BYTES}")
    declared_volumes = image.attrs.get("Config", {}).get("Volumes") or {}
    if declared_volumes:
        raise RuntimeError(f"Agent 镜像不能声明 VOLUME（会绕过只读根文件系统）: {', '.join(declared_volumes)}")
    base_report: dict[str, Any] = {
        "scanner": "docker-policy",
        "image_id": image.id,
        "size_bytes": size,
        "rootfs_layers": len(image.attrs.get("RootFS", {}).get("Layers", [])),
        "status": "passed",
    }
    fallback_sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "metadata": {"component": {"type": "container", "name": image_ref, "version": image.id}},
        "components": [],
    }
    if not settings.AGENT_TRIVY_PATH:
        if settings.ENVIRONMENT.lower() == "production":
            raise RuntimeError("生产环境必须配置 AGENT_TRIVY_PATH")
        base_report["warning"] = "Trivy 未配置；仅执行本地镜像策略检查"
        return ImageSecurityResult(base_report, fallback_sbom)

    scan = _run_trivy(["image", "--format", "json", "--severity", "CRITICAL", "--exit-code", "1", image_ref])
    sbom = _run_trivy(["image", "--format", "cyclonedx", image_ref])
    base_report.update({"scanner": "trivy", "vulnerabilities": json.loads(scan.stdout or "{}")})
    return ImageSecurityResult(base_report, json.loads(sbom.stdout or "{}"))


def _run_trivy(args: list[str]) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    if settings.AGENT_BUILDER_DOCKER_HOST:
        environment["DOCKER_HOST"] = settings.AGENT_BUILDER_DOCKER_HOST
    result = subprocess.run(
        [settings.AGENT_TRIVY_PATH, *args],
        capture_output=True,
        text=True,
        timeout=settings.AGENT_IMAGE_SCAN_TIMEOUT_SECONDS,
        check=False,
        env=environment,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Trivy 镜像扫描未通过: {(result.stderr or result.stdout)[-2000:]}")
    return result
