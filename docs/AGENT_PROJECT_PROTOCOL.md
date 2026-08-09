# Agent project protocol v1

This is the normative upload contract. The platform retains the original ZIP,
TAR.GZ or TGZ and requires `agent-eval.yaml` at the project root.

## Three independent contracts

- Deployment: Compose describes services and dependencies; Dockerfile is the
  compatible single-service form.
- Invocation: HTTP (Compose and image) or JSON stdio (image only) transports a
  versioned task envelope and returns `{result, trace}`.
- Evaluation: generated and private Rubrics remain inside the platform and are
  supplied only to evaluators. They are never copied into the Agent container.

## Recommended Compose manifest

```yaml
schema_version: 1
deployment:
  type: compose
  file: docker-compose.yml
  entry_service: agent
runtime:
  protocol: http
  port: 8080
  healthcheck: /health
  invoke: /v1/evaluations/run
  reset: /v1/evaluations/reset
  startup_timeout_seconds: 120
  timeout_seconds: 300
  state_scope: evaluation
security:
  network: restricted
  allowed_domains: [api.openai.com]
```

For one service, use `deployment.type: image` and add `build.dockerfile` and
`build.context`. Compose deployments use HTTP because a long-lived entry
service provides a stable boundary independent of its internal language or CLI.

## Compose safety subset

The uploaded Compose file is parsed as deployment intent and is never executed
directly. The platform rejects privileged mode, host networking/PID/IPC,
devices, added capabilities, host ports, bind mounts, external configs/secrets,
container names and shell-form commands. A service must use a pinned external
image tag/digest or a local build. Named volumes may be declared with empty
top-level definitions; the platform rewrites them to evaluation-scoped volumes
and deletes them during cleanup.

The runtime creates one internal network, applies CPU/memory/PID/log limits,
drops all capabilities and enables `no-new-privileges`. The entry service is
non-root and read-only. Dependency services may use their image user and only
receive writable temporary named volumes needed by databases.

## Invocation envelope

```json
{
  "protocol_version": "1.0",
  "evaluation_id": "eval-123",
  "case_id": "case-1",
  "task": {"id": "case-1", "input": "..."},
  "guidance": {"language": "zh-CN", "output_format": "markdown"},
  "runtime": {"deadline_seconds": 300, "trace_level": "tool_calls"}
}
```

The response is one JSON object:

```json
{"result":{"status":"success","output":"..."},"trace":{"spans":[]}}
```

`guidance` contains only user-visible task constraints. AI-generated Rubrics,
weights, reference answers, judge prompts and private pass conditions are never
present in this envelope. After the Agent returns, evaluators receive the
result, trace and the frozen full Rubric.

