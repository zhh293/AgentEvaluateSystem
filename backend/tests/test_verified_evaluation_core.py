import json
from pathlib import Path

import pytest

from app.core.exceptions import ValidationException
from app.engine.case_set_validator import recommended_case_count, validate_case_set
from app.engine.rubric_evaluator import evaluate_rubric
from app.schemas.internal.case_set import GeneratedCase
from app.schemas.request.intake import RuntimeConfigUpload
from app.services.agent_package import compile_uploaded_contract
from app.services.capability_service import parse_interface_spec
from app.services.manifest_service import bind_service_images, compile_verified_manifest


def runtime_config(**overrides):
    payload = {
        "schema_version": 1,
        "entry_service": "agent",
        "runtime": {"protocol": "http", "port": 8080, "healthcheck": {"path": "/health"}},
        "environment": {"public": {"LOG_LEVEL": "info"}, "secret_refs": [
            {"target": "OPENAI_API_KEY", "source": "evaluation.llm_api_key"}
        ]},
        "network": {"mode": "restricted", "allowed_domains": ["api.openai.com"]},
    }
    payload.update(overrides)
    return RuntimeConfigUpload.model_validate(payload)


def test_runtime_config_rejects_secret_in_public_environment():
    with pytest.raises(ValueError, match="secret_refs"):
        runtime_config(environment={"public": {"API_KEY": "secret"}})


def test_compile_uploaded_compose_without_user_manifest(tmp_path: Path):
    (tmp_path / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    compose = b"""services:
  agent:
    build:
      context: .
      dockerfile: Dockerfile
"""
    contract = compile_uploaded_contract(tmp_path, compose, runtime_config())
    assert contract.deployment.type == "compose"
    assert contract.deployment.entry_service == "agent"
    assert contract.runtime.protocol == "http"
    assert not (tmp_path / ".agenteval-uploaded-compose.yaml").exists()


def test_openapi_capabilities_keep_source_and_exact_operation():
    spec = {
        "openapi": "3.1.0",
        "info": {"title": "Agent", "version": "1"},
        "paths": {"/users": {"post": {"operationId": "createUser", "responses": {"201": {"description": "ok"}}}}},
    }
    catalog = parse_interface_spec(json.dumps(spec).encode(), "openapi.json")
    assert catalog.spec_type == "openapi"
    assert catalog.capabilities[0].key == "HTTP:POST:/users"
    assert catalog.capabilities[0].source_pointer == "#/paths/~1users/post"


def test_openapi_resolves_local_refs_and_rejects_remote_refs():
    spec = {
        "openapi": "3.0.3",
        "paths": {"/echo": {"post": {"requestBody": {"$ref": "#/components/requestBodies/Echo"}, "responses": {"200": {"description": "ok"}}}}},
        "components": {"requestBodies": {"Echo": {"content": {"application/json": {"schema": {"type": "object"}}}}}},
    }
    catalog = parse_interface_spec(json.dumps(spec).encode(), "openapi.json")
    body = catalog.capabilities[0].input_schema["request_body"]
    assert body["content"]["application/json"]["schema"]["type"] == "object"
    spec["paths"]["/echo"]["post"]["requestBody"] = {"$ref": "https://example.com/schema.yaml"}
    with pytest.raises(ValidationException, match="文档内"):
        parse_interface_spec(json.dumps(spec).encode(), "openapi.json")


def test_cli_capabilities_require_structured_argv():
    spec = b"""schema_version: 1
type: cli
executable: [python, -m, agent]
commands:
  - id: summarize
    args: [summarize]
    description: summarize text
"""
    catalog = parse_interface_spec(spec, "cli.yaml")
    assert catalog.capabilities[0].operation["executable"] == ["python", "-m", "agent"]


def test_manifest_rejects_reserved_environment_and_binds_images(tmp_path: Path):
    (tmp_path / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    contract = compile_uploaded_contract(tmp_path, b"services:\n  agent:\n    build: .\n", runtime_config())
    with pytest.raises(ValueError, match="保留环境变量"):
        compile_verified_manifest("s", "a", "b", "c", "d", contract, {"HTTP_PROXY": "x"}, [])
    manifest = compile_verified_manifest("s", "a", "b", "c", "d", contract, {}, []).payload
    bound = bind_service_images(manifest, {"agent": "registry/agent@sha256:" + "a" * 64})
    assert bound["deployment"]["services"][0]["dockerfile"] is None
    assert "@sha256:" in bound["deployment"]["services"][0]["image"]


def _case(case_id: str, path: str = "/users") -> GeneratedCase:
    return GeneratedCase.model_validate({
        "id": case_id, "title": f"Create user {case_id}", "suite": "functional", "horizon": "short",
        "capability_ids": ["HTTP:POST:/users"],
        "invocation": {"protocol": "http", "service": "agent", "method": "POST", "path": path, "body": {}},
        "rubrics": [{
            "id": f"R-{case_id}", "dimension": "result", "assertion": "returns created status",
            "judge_type": "programmatic", "evidence_required": ["http.status"],
            "pass_condition": {"path": "http.status", "operator": "eq", "value": 201},
        }],
    })


def test_case_validator_proves_coverage_and_invocation_match():
    cases = [_case(f"C-{index:02d}") for index in range(30)]
    # Give each case a distinct body to avoid genuine invocation duplicates.
    for index, case in enumerate(cases):
        case.invocation.body = {"index": index}
    report = validate_case_set(cases, {
        "HTTP:POST:/users": {"kind": "http", "operation": {"method": "POST", "path": "/users"}}
    }, 30, entry_service="agent")
    assert report.valid
    assert report.coverage["coverage_rate"] == 1.0


def test_case_validator_rejects_hallucinated_path():
    cases = [_case(f"C-{index:02d}", path="/invented") for index in range(30)]
    for index, case in enumerate(cases):
        case.invocation.body = {"index": index}
    report = validate_case_set(cases, {
        "HTTP:POST:/users": {"kind": "http", "operation": {"method": "POST", "path": "/users"}}
    }, 30, entry_service="agent")
    assert not report.valid
    assert any("HTTP 调用" in error for error in report.errors)


@pytest.mark.asyncio
async def test_programmatic_rubric_uses_evidence_and_unknown_is_not_zero():
    rubric = {
        "id": "R1", "dimension": "result", "assertion": "status is created",
        "judge_type": "programmatic", "evidence_required": ["http.status"],
        "pass_condition": {"path": "http.status", "operator": "eq", "value": 201}, "weight": 1,
    }
    passed = await evaluate_rubric(rubric, {"http": {"status": 201}}, [])
    unknown = await evaluate_rubric(rubric, {"http": {}}, [])
    assert passed.verdict == "pass" and passed.score == 100
    assert unknown.verdict == "unknown" and unknown.score is None


def test_dynamic_case_budget_stays_within_product_bounds():
    assert recommended_case_count(2, "short") == 30
    assert recommended_case_count(12, "long") == 40
    assert recommended_case_count(100, "short") == 60
