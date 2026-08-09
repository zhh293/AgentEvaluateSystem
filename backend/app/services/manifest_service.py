from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.services.agent_package import AgentPackageContract


GENERATOR_VERSION = "1.0.0"
_RESERVED_ENV = {
    "AGENTEVAL_EVALUATION_ID",
    "AGENTEVAL_CASE_ID",
    "AGENTEVAL_ATTEMPT_ID",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
}


@dataclass(frozen=True)
class CompiledManifest:
    payload: dict[str, Any]
    input_digest: str
    manifest_digest: str


def compile_verified_manifest(
    submission_id: str,
    source_digest: str,
    compose_digest: str,
    runtime_digest: str,
    interface_spec_digest: str,
    contract: AgentPackageContract,
    public_environment: dict[str, str],
    secret_bindings: list[dict[str, str]],
) -> CompiledManifest:
    conflicts = sorted(_RESERVED_ENV.intersection(public_environment))
    if conflicts:
        raise ValueError(f"运行配置试图覆盖平台保留环境变量: {', '.join(conflicts)}")
    input_digest = _digest({
        "source": source_digest,
        "compose": compose_digest,
        "runtime": runtime_digest,
        "interface_spec": interface_spec_digest,
    })
    contract_payload = contract.as_dict()
    payload = {
        "schema_version": 1,
        "submission_id": submission_id,
        "input_digest": input_digest,
        "entry_service": contract.deployment.entry_service,
        "deployment": contract_payload["deployment"],
        "runtime": contract_payload["runtime"],
        "network_policy": contract_payload["security"],
        "environment": {
            "public": dict(sorted(public_environment.items())),
            "secret_bindings": sorted(secret_bindings, key=lambda item: item["target"]),
        },
        "security_baseline": {
            "read_only_rootfs": True,
            "cap_drop": ["ALL"],
            "no_new_privileges": True,
            "host_bind_mounts": False,
            "host_network": False,
            "privileged": False,
        },
        "generator": {
            "version": GENERATOR_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    return CompiledManifest(payload, input_digest, _digest(payload))


def bind_service_images(manifest: dict[str, Any], service_images: dict[str, str]) -> dict[str, Any]:
    """Return an immutable post-build manifest with every service image pinned."""
    result = json.loads(json.dumps(manifest))
    missing: list[str] = []
    for service in result["deployment"]["services"]:
        image = service_images.get(service["name"])
        if not image:
            missing.append(service["name"])
            continue
        service["image"] = image
        service["dockerfile"] = None
        service["context"] = None
    if missing:
        raise ValueError(f"构建结果缺少服务镜像: {', '.join(sorted(missing))}")
    result["image_binding_digest"] = _digest(service_images)
    return result


def manifest_contract_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    """Project the verified manifest back to the existing runtime contract."""
    return {
        "schema_version": manifest["schema_version"],
        "deployment": manifest["deployment"],
        "build": {"mode": "compose", "dockerfile": None, "context": "."},
        "runtime": manifest["runtime"],
        "security": manifest["network_policy"],
        "manifest_path": "verified-manifest.json",
    }


def _digest(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
