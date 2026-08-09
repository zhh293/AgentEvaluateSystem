from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.request.submission import SubmissionConfigRequest
from app.services.agent_type_identifier import TypeIdentificationResult
from app.services.model_connectivity import ConnectivityResult
from app.services.security_service import SecurityScanResult, ScanStatus
from app.services.submission_service import submission_service
from app.services.agent_package import AgentPackageContract, BuildContract, DeploymentContract, RuntimeContract, SecurityContract


def _config() -> SubmissionConfigRequest:
    return SubmissionConfigRequest(
        agent_name="secret-test",
        description="A sufficiently detailed test agent description for validation.",
        llm_provider="openai",
        llm_model="test-model",
        llm_api_base="https://example.invalid/v1",
        llm_api_key="sk-must-never-be-persisted",
    )


@pytest.mark.asyncio
async def test_pipeline_never_persists_llm_api_key():
    connectivity = ConnectivityResult(ok=True, model="test-model")
    scan = SecurityScanResult(status=ScanStatus.PASSED)
    identification = TypeIdentificationResult(
        agent_type="short_horizon", subtype="conversational", confidence=1.0
    )
    contract = AgentPackageContract(
        schema_version=1,
        deployment=DeploymentContract(type="image", entry_service="agent"),
        build=BuildContract(mode="dockerfile", dockerfile="Dockerfile"),
        runtime=RuntimeContract(),
        security=SecurityContract(),
        manifest_path="agent-eval.yaml",
    )

    with (
        patch("app.services.submission_service.validate_and_extract"),
        patch("app.services.submission_service._extract_package"),
        patch("app.services.submission_service._cleanup_dir"),
        patch("app.services.submission_service._read_requirements", return_value=""),
        patch("app.services.submission_service.load_package_contract", return_value=contract),
        patch("app.services.submission_service.validate_dockerfile"),
        patch(
            "app.services.submission_service.connectivity_checker.check",
            AsyncMock(return_value=connectivity),
        ),
        patch("app.services.submission_service.security_scanner.full_audit", return_value=scan),
        patch(
            "app.services.submission_service.agent_type_identifier.identify",
            AsyncMock(return_value=identification),
        ),
    ):
        result = await submission_service.run_pipeline(_config(), b"package", "agent.zip")

    assert "llm_api_key" not in result.submission.config
    assert "sk-must-never-be-persisted" not in repr(result.submission.config)
