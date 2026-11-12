# CodeAct Runtime

CodeAct Runtime is a from-scratch educational agent execution framework inspired by the ICML
2024 CodeAct paper. A model proposes Python or Bash as an action; the runtime evaluates policy,
executes accepted code in a disposable Docker container, and returns bounded output and errors so
the model can correct its next step.

## Current status

M0 and M1 are implemented and locally verified:

- typed Python/Bash actions, observations, step records, and terminal results;
- model-action-policy-execution-observation loop;
- completion, maximum-step, consecutive-failure, and denied-approval stop conditions;
- deny-by-default approval for statically detected high-risk behavior;
- disposable Docker execution with networking disabled, resource limits, non-root UID, dropped
  capabilities, no-new-privileges, timeouts, and output truncation;
- isolated run workspaces plus pre-mutation snapshots and automatic rollback after failed or
  timed-out write actions;
- one-time approvals bound to the exact action SHA-256, risk reasons, approver, and expiration;
- append-only, secret-redacted JSONL audit events with a verifiable SHA-256 hash chain;
- conservative approval for dynamic or encoded shell execution, process exhaustion, nested
  Python execution, deletion, networking, permission changes, and Docker daemon operations;
- rejection of pre-existing workspace symlinks that resolve outside the workspace boundary;
- Python 3.12 packaging, Docker test image, Ruff/pytest/coverage gates, and CI.

M2 is implemented and locally verified: an allowlisted stdio MCP client performs the pinned 2025-11-25
initialize lifecycle, validates JSON-RPC framing and capabilities, and discovers paginated tools.
Discovered tools use Draft 2020-12 argument validation and host-owned risk rules; mutating or
high-risk calls require a one-time grant bound to the exact server, tool, and arguments.
Results are shape-validated, explicitly wrapped as untrusted model data, bounded in size, and
recorded through the secret-redacted hash-chain audit. A real fixture server verifies discovery,
denial before approval, exact approved mutation, injected result handling, and audit redaction.

M3-A is implemented: a bounded generic warm-sandbox pool provides explicit startup, acquisition
timeouts, health checks, idempotent leases, dirty-instance destruction, asynchronous clean
replacement, statistics, and deterministic shutdown. M3-B adds a real Docker backend whose
prestarted containers use an in-memory `/workspace`, retain state across actions in one lease,
and are destroyed instead of reused when the lease ends. The containers run non-root with no
network, a read-only root filesystem, dropped capabilities, no-new-privileges, and CPU, memory,
PID, workspace, execution-time, and output limits.

This checkpoint does not yet claim measured warm-start latency, concurrent isolation acceptance,
a SWE-bench result, model-quality improvement, or an OpenHands contribution. Those are
evidence-gated milestones in requirements.md.

## Local quality gates

Python 3.12 is required.

~~~bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
ruff check .
pytest --cov=codeact --cov-report=term-missing --cov-fail-under=90
docker compose config --quiet
~~~

The default tests mock the process boundary while checking isolation flags. M1 also provides
opt-in real-Docker tests and scripts/verify_m1.py, which verifies non-root writes, network denial,
and failed-action rollback. This remains a development sandbox, not a production security claim.

## Documents

- [V1 requirements and evidence rules](requirements.md)
- [Architecture and trust boundaries](docs/architecture.md)
- [Runtime contract](docs/api-contract.md)
- [Experiment protocol](docs/experiments/README.md)
- [MCP integration](docs/mcp.md)
- [Chinese learning notes](CodeAct学习笔记.txt)
