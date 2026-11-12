# M3 warm-pool isolation acceptance - 2026-11-12

## Scope

This verifies the local M3-C implementation. It is a functional lifecycle and configuration check,
not a penetration test or production multi-tenant isolation certification.

## Environment

- Host: macOS 15.3.1 (24D70), Docker Desktop
- Docker client/server: 27.4.0 / 27.4.0
- Image: `python:3.12.10-slim`
- Image digest: `sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db`
- Base commit before M3-C changes: `d265a3c1739a9768bae0493d2952d68987c8a0ac`
- Pool size: 2

## Reproduction

~~~bash
PYTHONPATH=backend python3 scripts/verify_m3.py
~~~

## Checks and result

- Two actions in one lease observed the same tmpfs workspace state.
- The next lease used a different container ID and did not contain `secret.txt`.
- Docker inspection confirmed network mode `none`, a read-only root filesystem, all capabilities
  dropped, and non-zero memory plus configured PID limits.
- Unit stress with six concurrent workers observed at most two active leases for pool size two.
- A fake backend that failed two replacement attempts recovered to full capacity and reported both
  failures.

Result: passed. Real container IDs were `766c4a745393` and `af3cc7b9507d`; both were removed by the
pool lifecycle.

## Limitations

The check does not test kernel or Docker daemon escape resistance. Container IDs and timings vary
per run. Cold-versus-warm latency measurement belongs to M3-D and is not claimed here.
