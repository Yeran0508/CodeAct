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

M3-C verifies that concurrent acquisition never exceeds the configured capacity, transient
replacement failures recover without silently shrinking the pool, and unhealthy instances are
discarded. `scripts/verify_m3.py` performs a real-Docker check for same-session state, different
container IDs, zero workspace leakage across sessions, and active network, root-filesystem,
capability, PID, and memory controls.

M3-D completes the milestone with a reproducible 12-sample Docker benchmark. On the recorded
macOS/Docker Desktop environment, cold create-plus-execute measured 701.654 ms P50 and 935.908 ms
P95; warm health-check-plus-execute measured 241.200 ms P50 and 297.220 ms P95, a 65.62% P50
reduction. Prewarming and asynchronous replacement are intentionally outside the warm timed region.

M4-A begins context management with one deterministic truncation primitive that returns original
and removed character metadata, preserves useful head/tail evidence, handles Unicode, and strictly
honors zero or marker-only budgets.

M4-B adds deterministic structured history summaries. They preserve first-seen paths, exact stderr,
policy/approval/rollback/exit decisions, and unresolved failures without asking a model to
paraphrase evidence; canonical JSON makes identical inputs byte-stable.

M4-C separates a SHA-256-identified stable prompt prefix from dynamic task/history data. Optional
model responses carry provider-reported input, output, cache-read, and cache-write token counts;
the runtime aggregates those values and audits them without substituting character estimates.

M4-D completes the milestone with a deterministic 10-case long-history comparison under the same
2,400-character dynamic budget and stable prefix. Direct history truncation retained all required
path/error/decision/unresolved facts in 0/10 cases; structured summaries retained them in 10/10 and
used 13,389 versus 13,715 fixture-provider input tokens (2.38% fewer). Both modes reported 963
cache-read tokens. This measures synthetic fact retention and fixture accounting, not LLM accuracy.

M5-A adds a bounded parallel evaluation runner with unique clean task workspaces, atomic JSON
manifests, payload-digest validation, crash recovery, failed-attempt retry, and completed-task
resume. Benchmark workers—not host directories—remain responsible for one clean sandbox per task.

M5-B adds the representation-neutral `codeact-local-v1` dataset and Docker harness. Six deterministic
file tasks share validated setup, action/time budgets, and trusted evaluators; each task performs
setup, candidate actions, and evaluation inside one clean container that is destroyed afterward.
`PYTHONPATH=backend python3 scripts/verify_m5_local.py` verifies all six tasks in parallel and then
confirms that manifest resume skips every completed result.

M5-C adds two round-tripped action codecs around one seeded semantic fixture model. Code-action and
canonical JSON-tool modes share prompts, plans, Docker execution, evaluator, and enforced action,
input-token, and output-token budgets; only the serialized action representation changes.

M5-D completes the local evaluation milestone. On six deterministic tasks, both modes passed 6/6
with zero retries, timeouts, or failures and identical 216 input tokens. The fixture reported 353
Code-action versus 696 JSON-tool output tokens. Raw manifests include per-task latency and usage;
the aggregate includes P50/P95 latency and failure categories. This is harness evidence using a
semantic fixture—not a production-model comparison—and no SWE-bench result is claimed.

This checkpoint does not claim a SWE-bench result, model-quality improvement, production security
certification, or an OpenHands contribution. Those are evidence-gated or explicitly out-of-scope
claims in requirements.md.

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
and failed-action rollback. `PYTHONPATH=backend python3 scripts/verify_m3.py` runs the M3 isolation
acceptance. `PYTHONPATH=backend:. python3 scripts/benchmark_m3.py --iterations 12 --pool-size 2`
reproduces the latency protocol. This remains a development sandbox, not a production security
claim.

## Documents

- [V1 requirements and evidence rules](requirements.md)
- [Architecture and trust boundaries](docs/architecture.md)
- [Runtime contract](docs/api-contract.md)
- [Experiment protocol](docs/experiments/README.md)
- [M3 isolation acceptance](docs/experiments/2026-11-12-m3-isolation-acceptance.md)
- [M3 cold-versus-warm benchmark](docs/experiments/2026-11-12-m3-warm-pool-benchmark.md)
- [M4 long-context summary comparison](docs/experiments/2026-11-12-m4-summary-comparison.md)
- [M5 equal-budget baseline comparison](docs/experiments/2026-11-12-m5-baseline-comparison.md)
- [MCP integration](docs/mcp.md)
- [Chinese learning notes](CodeAct学习笔记.txt)
