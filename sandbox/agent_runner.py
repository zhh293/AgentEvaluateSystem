"""Execute an uploaded Agent through a small, deterministic JSON contract."""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from otel_instrument import TraceRecorder


def _load_agent(agent_file: Path):
    spec = importlib.util.spec_from_file_location("submitted_agent", agent_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {agent_file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _entrypoint(module):
    for name in ("run", "run_agent", "main"):
        candidate = getattr(module, name, None)
        if callable(candidate):
            return candidate
    agent_class = getattr(module, "Agent", None)
    if agent_class:
        instance = agent_class()
        for name in ("run", "invoke", "execute"):
            candidate = getattr(instance, name, None)
            if callable(candidate):
                return candidate
    raise RuntimeError("agent.py must expose run/run_agent/main or Agent.run/invoke/execute")


def run_agent_task(task: dict[str, Any], agent_module, recorder: TraceRecorder) -> dict[str, Any]:
    started = time.perf_counter()
    entrypoint = _entrypoint(agent_module)
    with recorder.span("AGENT_EXECUTION", {"task.id": str(task.get("id", ""))}):
        value = entrypoint(task)
        if inspect.isawaitable(value):
            import asyncio

            value = asyncio.run(value)
    return {
        "status": "success",
        "output": value,
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        "transcript": recorder.spans,
    }


def _apply_resource_limits(cpu_seconds: int, memory_mb: int, processes: int) -> None:
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.setrlimit(resource.RLIMIT_AS, (memory_mb * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_NPROC, (processes, processes))
    except (ImportError, ValueError, OSError):
        # Containers still enforce cgroup limits; resource is unavailable on Windows.
        return


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-file", required=True)
    parser.add_argument("--output", default="/tmp/result.json")
    parser.add_argument("--agent-file", default="/agent/agent.py")
    parser.add_argument("--trace-output", default="/tmp/trace.json")
    parser.add_argument("--cpu-seconds", type=int, default=300)
    parser.add_argument("--memory-mb", type=int, default=512)
    parser.add_argument("--max-processes", type=int, default=64)
    args = parser.parse_args()

    _apply_resource_limits(args.cpu_seconds, args.memory_mb, args.max_processes)
    recorder = TraceRecorder()
    result: dict[str, Any]
    try:
        task = json.loads(Path(args.task_file).read_text(encoding="utf-8"))
        module = _load_agent(Path(args.agent_file))
        result = run_agent_task(task, module, recorder)
    except Exception as exc:
        result = {
            "status": "error",
            "error": str(exc),
            "traceback": traceback.format_exc(limit=20),
            "transcript": recorder.spans,
        }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, default=str), encoding="utf-8")
    Path(args.trace_output).write_text(recorder.to_json(), encoding="utf-8")
    # Never include secret environment variables in output or trace attributes.
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
