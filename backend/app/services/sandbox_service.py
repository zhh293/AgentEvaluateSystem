"""Docker-backed sandbox lifecycle with hard timeouts and least privilege."""

from __future__ import annotations

import asyncio
import io
import shlex
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.exceptions import ValidationException
from app.core.metrics import SANDBOX_ACTIVE, SANDBOX_RUNS, SANDBOX_TIMEOUTS


SANDBOX_IMAGE_MAP = {
    "low": settings.SANDBOX_IMAGE_READONLY,
    "medium": settings.SANDBOX_IMAGE_WRITABLE,
    "high": settings.SANDBOX_IMAGE_HIGHRISK,
}


@dataclass(frozen=True)
class SandboxLimits:
    memory_bytes: int = 512 * 1024 * 1024
    nano_cpus: int = 1_000_000_000
    pids_limit: int = 64


class SandboxManager:
    def __init__(self, client: Any | None = None):
        if client is None:
            try:
                import docker
            except ImportError as exc:
                raise RuntimeError("Docker SDK is not installed") from exc
            client = docker.from_env()
        self.client = client

    @staticmethod
    def image_for_risk(risk_level: str) -> str:
        try:
            return SANDBOX_IMAGE_MAP[risk_level.lower()]
        except KeyError as exc:
            raise ValidationException(f"未知沙箱风险等级: {risk_level}") from exc

    async def create_sandbox(
        self,
        submission_id: str,
        image: str,
        source_path: str,
        timeout: int = 300,
        *,
        environment: dict[str, str] | None = None,
        network_enabled: bool = False,
        writable: bool = False,
        limits: SandboxLimits | None = None,
    ) -> str:
        source = Path(source_path).resolve()
        if not source.exists() or not source.is_dir():
            raise ValidationException(f"沙箱源码目录不存在: {source}")
        limits = limits or SandboxLimits()

        def create() -> Any:
            try:
                self.client.images.get(image)
            except Exception:
                self.client.images.pull(image)
            container = self.client.containers.create(
                image=image,
                name=f"agenteval-{submission_id}",
                entrypoint=["sleep", "infinity"],
                command=None,
                detach=True,
                environment=environment or {},
                network_mode=None if network_enabled else "none",
                read_only=not writable,
                mem_limit=limits.memory_bytes,
                nano_cpus=limits.nano_cpus,
                pids_limit=limits.pids_limit,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                user="sandbox",
                tmpfs={
                    "/tmp": "rw,noexec,nosuid,size=64m",
                    "/agent": "rw,noexec,nosuid,size=128m",
                },
                labels={"agenteval.submission_id": submission_id},
            )
            try:
                container.start()
                archive = io.BytesIO()
                with tarfile.open(fileobj=archive, mode="w") as tf:
                    for path in source.rglob("*"):
                        if path.is_file():
                            tf.add(path, arcname=path.relative_to(source).as_posix(), recursive=False)
                archive.seek(0)
                if not container.put_archive("/agent", archive.read()):
                    raise RuntimeError("failed to copy Agent source into sandbox")
                if writable:
                    ownership = container.exec_run(["chown", "-R", "sandbox:sandbox", "/agent"], user="0")
                    if int(ownership.exit_code) != 0:
                        raise RuntimeError("failed to prepare writable Agent workspace")
                return container
            except Exception:
                try:
                    container.remove(force=True, v=True)
                except Exception:
                    pass
                raise

        try:
            container = await asyncio.wait_for(asyncio.to_thread(create), timeout=timeout)
            SANDBOX_ACTIVE.inc()
            return container.id
        except asyncio.TimeoutError as exc:
            raise TimeoutError(f"创建沙箱超过 {timeout} 秒") from exc

    async def execute_in_sandbox(
        self, container_id: str, command: str | list[str], timeout: int = 300
    ) -> tuple[int, str, str]:
        container = await asyncio.to_thread(self.client.containers.get, container_id)
        argv = shlex.split(command) if isinstance(command, str) else command

        def execute() -> tuple[int, str, str]:
            result = container.exec_run(argv, demux=True)
            stdout_raw, stderr_raw = result.output or (b"", b"")
            return (
                int(result.exit_code),
                (stdout_raw or b"").decode("utf-8", errors="replace"),
                (stderr_raw or b"").decode("utf-8", errors="replace"),
            )

        try:
            SANDBOX_RUNS.inc()
            return await asyncio.wait_for(asyncio.to_thread(execute), timeout=timeout)
        except asyncio.TimeoutError as exc:
            SANDBOX_TIMEOUTS.inc()
            await self.destroy_sandbox(container_id)
            raise TimeoutError(f"沙箱命令超过 {timeout} 秒并已强制销毁") from exc

    async def destroy_sandbox(self, container_id: str) -> None:
        try:
            container = await asyncio.to_thread(self.client.containers.get, container_id)
        except Exception:
            return

        def destroy() -> None:
            try:
                container.stop(timeout=2)
            except Exception:
                try:
                    container.kill()
                except Exception:
                    pass
            finally:
                try:
                    container.remove(force=True, v=True)
                except Exception:
                    pass

        await asyncio.to_thread(destroy)
        SANDBOX_ACTIVE.dec()

    async def run_agent(
        self,
        container_id: str,
        task_file: str = "/agent/task.json",
        output_file: str = "/tmp/result.json",
        timeout: int = 300,
    ) -> tuple[int, str, str]:
        return await self.execute_in_sandbox(
            container_id,
            [
                "python",
                "/sandbox/agent_runner.py",
                "--task-file",
                task_file,
                "--output",
                output_file,
            ],
            timeout=timeout,
        )


sandbox_manager: SandboxManager | None = None


def get_sandbox_manager() -> SandboxManager:
    global sandbox_manager
    if sandbox_manager is None:
        sandbox_manager = SandboxManager()
    return sandbox_manager
