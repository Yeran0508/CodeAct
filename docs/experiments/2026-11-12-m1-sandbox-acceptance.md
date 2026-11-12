# M1 sandbox acceptance - 2026-11-12

## Scope

This validates the local M1 implementation. It is a functional safety check, not a penetration
test or production isolation certification.

## Environment

- Host: macOS with Docker Desktop
- Client timezone/date: America/Chicago, 2026-11-12
- Action image: python:3.12.10-slim
- Executor: network none, resource/PID limits, all capabilities dropped, no-new-privileges,
  and host non-root UID/GID

## Reproduction

~~~bash
PYTHONPATH=backend python3 scripts/verify_m1.py
~~~

## Result

The real container ran as UID 501, wrote through the workspace bind mount, and failed a direct
outbound socket connection with exit code 1. A second action modified a file and raised an error;
the runtime reported rolled_back=true and restored the original content.

The Dockerized unit gate reported 37 passed, 2 integration tests skipped by default, 95.98%
coverage, and a passing Ruff check. Integration tests require an explicit flag because the normal
test container does not receive the privileged Docker socket.

## Limitations

- Docker shares the host kernel and is not a hardened multi-tenant boundary.
- Static policy is defense in depth, not a complete Bash or Python security proof.
- The hash-chained audit file is tamper-evident; an administrator can still delete it.
- Copy-based snapshots target small development workspaces.
- One outbound socket attempt is not a full network audit.
