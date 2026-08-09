# Sandbox images for AgentEvaluateSystem

This directory contains Dockerfile definitions for the three sandbox isolation levels.

- `Dockerfile.readonly` — Low risk: Read-only container, no network
- `Dockerfile.writable` — Medium risk: Writeable container with gVisor
- `Dockerfile.highrisk` — High risk: Firecracker microVM, full isolation
