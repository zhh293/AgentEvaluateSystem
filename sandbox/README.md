# Sandbox images for AgentEvaluateSystem

This directory contains Dockerfile definitions for the three sandbox isolation levels.

- `Dockerfile.readonly` — Low risk: Read-only container, no network
- `Dockerfile.writable` — Medium risk: Writeable container with gVisor
- `Dockerfile.highrisk` — High risk: Firecracker microVM, full isolation
- `Dockerfile.http-invoker` — platform-owned bridge that invokes HTTP Agents from the internal runtime network
- `Dockerfile.egress-proxy` — platform-owned Squid proxy enforcing the external-domain allowlist and denying private destinations
