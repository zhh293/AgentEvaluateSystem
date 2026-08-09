"""Run a built Agent image through the stdio or HTTP evaluation contract."""

from __future__ import annotations

import asyncio
import json
import socket
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.core.metrics import SANDBOX_ACTIVE, SANDBOX_RUNS, SANDBOX_TIMEOUTS
from app.services.agent_package import AgentPackageContract


@dataclass(frozen=True)
class AgentExecution:
    result: dict[str, Any]
    trace: dict[str, Any]
    stdout: str = ""


class AgentImageRuntime:
    def __init__(self, client: Any | None = None):
        if client is None:
            import docker
            client = docker.from_env()
        self.client = client

    async def execute(
        self,
        evaluation_id: str,
        image: str,
        contract: AgentPackageContract,
        task: dict[str, Any],
        environment: dict[str, str],
        risk_level: str = "low",
    ) -> AgentExecution:
        timeout = contract.runtime.timeout_seconds
        network = None
        if contract.runtime.protocol == "http" or contract.security.network == "restricted":
            network = await asyncio.to_thread(self._create_runtime_network, evaluation_id)
        proxy_container = None
        try:
            if network is not None and contract.security.network == "restricted":
                if not settings.AGENT_EGRESS_PROXY_CONTAINER:
                    raise RuntimeError("restricted 网络必须配置 AGENT_EGRESS_PROXY_CONTAINER")
                proxy_container = await asyncio.to_thread(self._ensure_egress_proxy)
                await asyncio.to_thread(network.connect, proxy_container, aliases=["agenteval-egress"])
        except Exception:
            if network is not None:
                if proxy_container is not None:
                    try:
                        await asyncio.to_thread(network.disconnect, proxy_container, force=True)
                    except Exception:
                        pass
                try:
                    await asyncio.to_thread(network.remove)
                except Exception:
                    pass
            raise
        try:
            container = await asyncio.to_thread(
                self._create, evaluation_id, image, contract, environment, network.name if network else "none", risk_level
            )
        except Exception:
            if network is not None:
                if proxy_container is not None:
                    try:
                        await asyncio.to_thread(network.disconnect, proxy_container, force=True)
                    except Exception:
                        pass
                try:
                    await asyncio.to_thread(network.remove)
                except Exception:
                    pass
            raise
        SANDBOX_ACTIVE.inc()
        try:
            if contract.runtime.protocol == "stdio":
                return await self._run_stdio(container, contract, task, timeout)
            return await self._run_http(container, contract, task, timeout, network.name)
        finally:
            await asyncio.to_thread(self._destroy, container)
            if network is not None:
                if proxy_container is not None:
                    try:
                        await asyncio.to_thread(network.disconnect, proxy_container, force=True)
                    except Exception:
                        pass
                try:
                    await asyncio.to_thread(network.remove)
                except Exception:
                    pass
            SANDBOX_ACTIVE.dec()

    def _create(self, evaluation_id: str, image: str, contract: AgentPackageContract, environment: dict[str, str], network_mode: str, risk_level: str):
        try:
            self.client.images.get(image)
        except Exception:
            auth_config = None
            if settings.AGENT_REGISTRY_USERNAME and settings.AGENT_REGISTRY_PASSWORD:
                auth_config = {"username": settings.AGENT_REGISTRY_USERNAME, "password": settings.AGENT_REGISTRY_PASSWORD}
            self.client.images.pull(image, auth_config=auth_config)
        env = {"HOME": "/tmp", "TMPDIR": "/tmp", **environment}
        if contract.security.network == "restricted" and contract.security.allowed_domains:
            if not settings.AGENT_EGRESS_PROXY:
                raise RuntimeError("声明 allowed_domains 时必须配置 AGENT_EGRESS_PROXY，运行时按默认拒绝策略终止")
            globally_allowed = {item.strip().lower() for item in settings.AGENT_EGRESS_ALLOWED_DOMAINS.split(",") if item.strip()}
            requested = {item.lower() for item in contract.security.allowed_domains}
            if not requested.issubset(globally_allowed):
                denied = ", ".join(sorted(requested - globally_allowed))
                raise RuntimeError(f"域名未被平台出口代理策略允许: {denied}")
            env.update({"HTTP_PROXY": settings.AGENT_EGRESS_PROXY, "HTTPS_PROXY": settings.AGENT_EGRESS_PROXY})
        runtime_name = {
            "low": settings.AGENT_RUNTIME_LOW,
            "medium": settings.AGENT_RUNTIME_MEDIUM,
            "high": settings.AGENT_RUNTIME_HIGH,
        }.get(risk_level.lower(), "")
        create_options = {"runtime": runtime_name} if runtime_name else {}
        return self.client.containers.create(
            image=image,
            name=f"agenteval-run-{evaluation_id}",
            command=contract.runtime.command,
            detach=True,
            environment=env,
            network_mode=network_mode,
            read_only=True,
            mem_limit=settings.AGENT_RUNTIME_MEMORY_BYTES,
            nano_cpus=settings.AGENT_RUNTIME_NANO_CPUS,
            pids_limit=settings.AGENT_RUNTIME_PIDS_LIMIT,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            user=settings.AGENT_RUNTIME_USER,
            tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"},
            stdin_open=contract.runtime.protocol == "stdio",
            log_config={"type": "local", "config": {"max-size": "10m", "max-file": "1"}},
            labels={"agenteval.evaluation_id": evaluation_id},
            **create_options,
        )

    def _create_runtime_network(self, evaluation_id: str):
        return self.client.networks.create(
            f"{settings.AGENT_RUNTIME_NETWORK}-{evaluation_id}",
            driver="bridge",
            internal=True,
            labels={"agenteval.managed": "true", "agenteval.evaluation_id": evaluation_id},
        )

    def _ensure_egress_proxy(self):
        try:
            proxy = self.client.containers.get(settings.AGENT_EGRESS_PROXY_CONTAINER)
            proxy.reload()
            if proxy.status != "running":
                proxy.start()
            return proxy
        except Exception:
            pass
        try:
            self.client.images.get(settings.AGENT_EGRESS_PROXY_IMAGE)
        except Exception:
            auth_config = None
            if settings.AGENT_REGISTRY_USERNAME and settings.AGENT_REGISTRY_PASSWORD:
                auth_config = {"username": settings.AGENT_REGISTRY_USERNAME, "password": settings.AGENT_REGISTRY_PASSWORD}
            self.client.images.pull(settings.AGENT_EGRESS_PROXY_IMAGE, auth_config=auth_config)
        try:
            proxy = self.client.containers.create(
                image=settings.AGENT_EGRESS_PROXY_IMAGE,
                name=settings.AGENT_EGRESS_PROXY_CONTAINER,
                detach=True,
                environment={"ALLOWED_DOMAINS": settings.AGENT_EGRESS_ALLOWED_DOMAINS},
                network_mode="bridge",
                read_only=True,
                mem_limit=256 * 1024 * 1024,
                nano_cpus=250_000_000,
                pids_limit=64,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                tmpfs={"/tmp": "rw,noexec,nosuid,size=64m,mode=1777"},
                labels={"agenteval.managed": "true", "agenteval.role": "egress-proxy"},
            )
            proxy.start()
            return proxy
        except Exception:
            # Another worker may have won the create-by-name race.
            return self.client.containers.get(settings.AGENT_EGRESS_PROXY_CONTAINER)

    async def _run_stdio(self, container: Any, contract: AgentPackageContract, task: dict[str, Any], timeout: int) -> AgentExecution:
        attached = await asyncio.to_thread(
            self.client.api.attach_socket,
            container.id,
            params={"stdin": 1, "stream": 1},
        )
        await asyncio.to_thread(container.start)
        raw_socket = getattr(attached, "_sock", attached)
        await asyncio.to_thread(raw_socket.sendall, (json.dumps(task, ensure_ascii=False) + "\n").encode("utf-8"))
        try:
            raw_socket.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        SANDBOX_RUNS.inc()
        try:
            wait_result = await asyncio.wait_for(asyncio.to_thread(container.wait), timeout=timeout)
        except asyncio.TimeoutError as exc:
            SANDBOX_TIMEOUTS.inc()
            raise TimeoutError(f"Agent 执行超过 {timeout} 秒") from exc
        finally:
            try:
                attached.close()
            except Exception:
                pass
        stdout = (await asyncio.to_thread(container.logs, stdout=True, stderr=False)).decode("utf-8", errors="replace")
        stderr = (await asyncio.to_thread(container.logs, stdout=False, stderr=True)).decode("utf-8", errors="replace")
        if int(wait_result.get("StatusCode", 1)) != 0:
            raise RuntimeError(f"Agent 容器退出码 {wait_result.get('StatusCode')}: {stderr[-2000:]}")
        if len(stdout.encode("utf-8")) > settings.AGENT_RUNTIME_MAX_OUTPUT_BYTES:
            raise RuntimeError("Agent 标准输出超过大小限制")
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Agent 标准输出不是单个 JSON 对象: {stdout[-1000:]}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Agent 标准输出必须是 JSON 对象")
        trace = payload.pop("trace", {"spans": []})
        result = payload.get("result", payload)
        if not isinstance(result, dict) or not isinstance(trace, dict):
            raise RuntimeError("Agent 输出中的 result 和 trace 必须是对象")
        return AgentExecution(result=result, trace=trace, stdout=stdout)

    async def _run_http(self, container: Any, contract: AgentPackageContract, task: dict[str, Any], timeout: int, network_name: str) -> AgentExecution:
        await asyncio.to_thread(container.start)
        try:
            self.client.images.get(settings.AGENT_HTTP_INVOKER_IMAGE)
        except Exception:
            auth_config = None
            if settings.AGENT_REGISTRY_USERNAME and settings.AGENT_REGISTRY_PASSWORD:
                auth_config = {"username": settings.AGENT_REGISTRY_USERNAME, "password": settings.AGENT_REGISTRY_PASSWORD}
            self.client.images.pull(settings.AGENT_HTTP_INVOKER_IMAGE, auth_config=auth_config)
        invoker = await asyncio.to_thread(
            self.client.containers.create,
            image=settings.AGENT_HTTP_INVOKER_IMAGE,
            name=f"agenteval-invoke-{container.name}",
            detach=True,
            stdin_open=True,
            network_mode=network_name,
            read_only=True,
            mem_limit=128 * 1024 * 1024,
            nano_cpus=250_000_000,
            pids_limit=32,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            environment={
                "AGENT_BASE_URL": f"http://{container.name}:{contract.runtime.port}",
                "AGENT_HEALTH_PATH": contract.runtime.healthcheck,
                "AGENT_INVOKE_PATH": contract.runtime.invoke,
                "AGENT_TIMEOUT_SECONDS": str(timeout),
            },
            tmpfs={"/tmp": "rw,noexec,nosuid,size=16m"},
            log_config={"type": "local", "config": {"max-size": "10m", "max-file": "1"}},
        )
        try:
            payload = await self._exchange_json(invoker, task, timeout)
        finally:
            await asyncio.to_thread(self._destroy, invoker)
        if not isinstance(payload, dict):
            raise RuntimeError("Agent HTTP 响应必须是 JSON 对象")
        trace = payload.pop("trace", {"spans": []})
        result = payload.get("result", payload)
        if not isinstance(result, dict) or not isinstance(trace, dict):
            raise RuntimeError("Agent HTTP 响应中的 result 和 trace 必须是对象")
        return AgentExecution(result=result, trace=trace)

    async def _exchange_json(self, container: Any, task: dict[str, Any], timeout: int) -> dict[str, Any]:
        attached = await asyncio.to_thread(self.client.api.attach_socket, container.id, params={"stdin": 1, "stream": 1})
        await asyncio.to_thread(container.start)
        raw_socket = getattr(attached, "_sock", attached)
        await asyncio.to_thread(raw_socket.sendall, (json.dumps(task, ensure_ascii=False) + "\n").encode("utf-8"))
        try:
            raw_socket.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        try:
            wait_result = await asyncio.wait_for(asyncio.to_thread(container.wait), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise TimeoutError("HTTP invoker 超时") from exc
        finally:
            try:
                attached.close()
            except Exception:
                pass
        stdout = (await asyncio.to_thread(container.logs, stdout=True, stderr=False)).decode("utf-8", errors="replace")
        stderr = (await asyncio.to_thread(container.logs, stdout=False, stderr=True)).decode("utf-8", errors="replace")
        if int(wait_result.get("StatusCode", 1)) != 0:
            raise RuntimeError(f"HTTP invoker 失败: {stderr[-2000:]}")
        if len(stdout.encode("utf-8")) > settings.AGENT_RUNTIME_MAX_OUTPUT_BYTES:
            raise RuntimeError("HTTP Agent 响应超过大小限制")
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("HTTP invoker 未返回有效 JSON") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("HTTP invoker 响应必须是对象")
        return payload

    @staticmethod
    def _destroy(container: Any) -> None:
        try:
            container.remove(force=True, v=True)
        except Exception:
            pass


agent_image_runtime: AgentImageRuntime | None = None


def get_agent_image_runtime() -> AgentImageRuntime:
    global agent_image_runtime
    if agent_image_runtime is None:
        agent_image_runtime = AgentImageRuntime()
    return agent_image_runtime
