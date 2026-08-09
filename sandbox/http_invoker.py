"""Platform-owned HTTP bridge used inside the Agent internal network."""

import asyncio
import json
import os
import sys

import httpx


async def main() -> int:
    base = os.environ["AGENT_BASE_URL"]
    health = os.environ.get("AGENT_HEALTH_PATH", "/health")
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
        method = str(task.get("method", "POST")).upper()
        path = str(task.get("path", "/invoke"))
        if not path.startswith("/") or "//" in path:
            print("Invalid invocation path", file=sys.stderr)
            return 3
        headers = task.get("headers") if isinstance(task.get("headers"), dict) else {}
        response = await client.request(method, base + path, headers=headers, json=task.get("body"), timeout=timeout)
        try:
            body = response.json()
        except ValueError:
            body = response.text
        print(json.dumps({
            "result": {"status": "success", "output": body, "http": {
                "status": response.status_code, "headers": dict(response.headers), "body": body,
            }},
            "trace": {"spans": []},
        }, ensure_ascii=False))
    return 0


raise SystemExit(asyncio.run(main()))
