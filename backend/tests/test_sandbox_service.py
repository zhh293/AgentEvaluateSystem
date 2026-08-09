from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.sandbox_service import SandboxManager


@pytest.fixture
def docker_client():
    client = MagicMock()
    container = MagicMock()
    container.id = "container-123"
    client.containers.create.return_value = container
    client.containers.get.return_value = container
    return client, container


@pytest.mark.asyncio
async def test_create_sandbox_uses_secure_defaults(tmp_path: Path, docker_client):
    client, container = docker_client
    manager = SandboxManager(client=client)

    container_id = await manager.create_sandbox(
        "submission-1", "agenteval/sandbox:readonly", str(tmp_path)
    )

    assert container_id == "container-123"
    container.start.assert_called_once()
    kwargs = client.containers.create.call_args.kwargs
    assert kwargs["network_mode"] == "none"
    assert kwargs["read_only"] is True
    assert kwargs["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in kwargs["security_opt"]
    assert kwargs["entrypoint"] == ["sleep", "infinity"]
    assert "/agent" in kwargs["tmpfs"]
    container.put_archive.assert_called_once()


@pytest.mark.asyncio
async def test_execute_returns_demultiplexed_output(docker_client):
    client, container = docker_client
    container.exec_run.return_value = SimpleNamespace(
        exit_code=7, output=(b"stdout", b"stderr")
    )
    manager = SandboxManager(client=client)

    assert await manager.execute_in_sandbox("container-123", "python agent.py") == (
        7,
        "stdout",
        "stderr",
    )


@pytest.mark.asyncio
async def test_writable_sandbox_changes_agent_workspace_ownership(tmp_path: Path, docker_client):
    client, container = docker_client
    container.exec_run.return_value = SimpleNamespace(exit_code=0, output=(b"", b""))
    await SandboxManager(client=client).create_sandbox(
        "submission-2", "agenteval/sandbox:writable", str(tmp_path), writable=True
    )
    assert client.containers.create.call_args.kwargs["read_only"] is False
    container.exec_run.assert_called_once_with(["chown", "-R", "sandbox:sandbox", "/agent"], user="0")


@pytest.mark.asyncio
async def test_destroy_is_idempotent_when_container_is_missing():
    client = MagicMock()
    client.containers.get.side_effect = RuntimeError("not found")
    await SandboxManager(client=client).destroy_sandbox("missing")


def test_risk_level_selects_image():
    assert SandboxManager.image_for_risk("low").endswith(":readonly")
    assert SandboxManager.image_for_risk("medium").endswith(":writable")
    assert SandboxManager.image_for_risk("high").endswith(":highrisk")
