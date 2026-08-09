# Dockerfile-first Agent protocol v1

This document is the normative contract between an uploaded Agent project and AgentEvaluateSystem. `README.md` is the operator guide; this file defines behavior implementations may rely on.

## Submission artifact

The uploaded ZIP/TAR.GZ/TGZ is retained unchanged as the audit source. A project root is either the archive root or its only top-level directory. It contains a `Dockerfile` and normally an `agent-eval.yaml`. If no Dockerfile exists, only a root-level legacy `agent.py` is accepted; the platform generates a Dockerfile and stdio adapter before building.

```yaml
schema_version: 1
build:
  dockerfile: Dockerfile
  context: .
runtime:
  protocol: stdio
  timeout_seconds: 300
security:
  network: none
  allowed_domains: []
```

Paths are relative to the project root, cannot escape it, and the Dockerfile must be inside the build context. `docker-compose.yml` and multi-container submissions are not part of v1.

## Stdio protocol

The platform starts the image's configured `ENTRYPOINT`/`CMD` and writes exactly one UTF-8 JSON object plus a newline to standard input. The Agent writes diagnostic logs to standard error and exactly one JSON object to standard output:

```json
{
  "result": {"status": "success", "output": "..."},
  "trace": {"spans": []}
}
```

The process must exit with code zero. Output is size-limited. This protocol works with any language and does not require a shell or platform files inside the user image.

## HTTP protocol

HTTP mode declares `port`, `healthcheck`, and `invoke`. The user port is never published to the host. The Agent and a short-lived platform HTTP invoker share a per-evaluation internal network. The invoker waits for a successful health check and then POSTs the task JSON. The response uses the same `result` and `trace` envelope as stdio.

## Network and credentials

`network: none` permits no external traffic. HTTP mode still receives a private per-evaluation network solely so the platform invoker can reach it. `network: restricted` requires every domain to be both declared and present in the operator's global allowlist. A platform-owned Squid proxy is temporarily connected to that evaluation network; it denies private/reserved destinations and all undeclared domains.

Upload credentials are used only for connectivity validation. Each evaluation start supplies a new runtime credential. It is encrypted under `evaluation_id`, never stored in submission metadata, and atomically retrieved and deleted by the worker.

## Build and image lifecycle

The durable state sequence is:

```text
build_queued -> building -> image_ready
                         -> build_failed
```

Production requires a dedicated builder Docker endpoint, a registry push, and Trivy. Builds default to no network. The platform rejects archive traversal, links/devices, common secret files, remote Dockerfile `ADD`, Docker Socket references, privileged flags, oversized files/images, and image-declared volumes. Successful images have a vulnerability report, CycloneDX SBOM, build log, content digest, and immutable registry reference.

At runtime the platform overrides user image security settings with a non-root UID, read-only root filesystem, dropped capabilities, `no-new-privileges`, internal/no networking, cgroup/PID limits, bounded logs, and a hard evaluation timeout. Optional OCI runtime names map low/medium/high risk levels to infrastructure-provided runtimes such as runc, gVisor, or Kata.
