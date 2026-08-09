"""Platform-owned HTTP bridge used inside the Agent internal network."""

import asyncio
import json
import os
import sys

import httpx


async def main() -> int:
    base = os.environ["AGENT_BASE_URL"]
    health = os.environ.get("AGENT_HEALTH_PATH", "/health")
    invoke = os.environ.get("AGENT_INVOKE_PATH", "/invoke")
    timeout = int(os.environ.get("AGENT_TIMEOUT_SECONDS", "300"))
    task = json.load(sys.stdin)
    async with httpx.AsyncClient(timeout=min(timeout, 30), trust_env=False) as client:
        deadline = asyncio.get_running_loop().time() + min(timeout, 60)
        while True:
            try:
                response = await client.get(base + health)
                if response.is_success:
                    break
            except httpx.HTTPError:
                pass
            if asyncio.get_running_loop().time() >= deadline:
                print("Agent HTTP health check timed out", file=sys.stderr)
                return 2
            await asyncio.sleep(0.5)
        response = await client.post(base + invoke, json=task, timeout=timeout)
        response.raise_for_status()
        print(json.dumps(response.json(), ensure_ascii=False))
    return 0


raise SystemExit(asyncio.run(main()))
