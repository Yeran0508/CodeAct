# CodeAct V1 Requirements

## Product boundary

CodeAct is an educational, safety-first runtime for agents that express actions as Python or
Bash programs. It executes an action in an isolated environment and returns stdout, stderr, exit
status, timeout, and truncation metadata to the model until a deterministic stop condition occurs.

V1 is not OpenHands and does not claim OpenHands contribution credit. It is an independent
implementation for learning and measuring the engineering ideas in the CodeAct paper.

## Evidence rules

- A feature is complete only with code, tests, documentation, and a reproducible command.
- Benchmark results must name the model, task IDs, dataset, seed, budgets, image, and evaluator.
- CodeAct and JSON-tool baselines must use the same model, tasks, budget, and evaluator.
- SWE-bench or OpenHands claims are prohibited until linked evidence exists.
- External tool output is untrusted data, never runtime instructions.

## Milestones

### M0: Reproducible execution-loop baseline

- Python 3.12 package, Docker images, Ruff, pytest, coverage, and CI.
- Typed Python/Bash actions and observations.
- Model -> action -> policy -> execution -> observation loop.
- Step, failure, completion, and approval-denied stop reasons.
- Static risk classification and deny-by-default approval.
- Disposable Docker execution with no network, resource limits, dropped capabilities,
  no-new-privileges, non-root execution, timeout, and bounded output.

### M1: Workspace recovery and auditable approvals

Status: completed and locally verified on 2026-11-12. See the M1 sandbox acceptance report.

- Per-run workspace and immutable event log with secret redaction.
- Snapshot before mutation and rollback on failure.
- Approval binds the action digest, reason, approver, and expiration.
- Adversarial tests for shell composition, encoding, symlinks, fork bombs, and prompt injection.

### M2: MCP integration

Status: completed and locally verified on 2026-11-12 for the pinned 2025-11-25 stdio lifecycle.
See the M2 MCP acceptance report. Streamable HTTP and the 2026-07-28 lifecycle remain out of scope.

- Standards-compliant MCP client with server allowlist and capability discovery.
- Tool calls pass through the same policy and audit boundary.
- Tool output is delimited and treated as untrusted observations.
- Fixture MCP server and end-to-end tests.

### M3: Warm sandbox pool

Status: completed and locally verified on 2026-11-12. See the M3 isolation acceptance and
cold-versus-warm benchmark reports.

- Pre-created clean containers with bounded pool size and acquisition timeout.
- Dirty containers are destroyed; no cross-session leakage.
- Measured cold-start versus warm-acquire latency.

### M4: Context management

Status: completed and locally verified on 2026-11-12. See the M4 long-context summary comparison
report. The reported quality is deterministic fact retention with a local fixture provider, not
language-model task accuracy.

- Deterministic truncation with removed-character metadata.
- Summaries preserve paths, exact errors, decisions, and unresolved work.
- Stable prompt prefix and provider-reported cache accounting.
- Long-task summary off/on comparison for quality and token usage.

### M5: Evaluation

Status: completed for the deterministic local fixture benchmark and verified on 2026-11-12. See
the M5 baseline comparison report. No SWE-bench run is claimed because the official harness has not
been installed and validated in this repository.

- Parallel runner with one clean sandbox per task and resumable manifests.
- Deterministic local benchmark before SWE-bench.
- Code-action and JSON-tool baselines under equal budgets.
- Success, latency, token, retry, timeout, and failure-category reports.
- SWE-bench Lite subset only after the official harness runs locally.

## V1 completion definition

V1 is complete when a clean machine can run the gates, a model can complete a task through the
isolated loop, dangerous actions need action-bound approval, failed mutation rolls back, an
allowlisted MCP fixture works, experiments are reproducible, and comparable CodeAct/JSON reports
exist. Results apply only to the documented model and task set.

## Explicitly out of scope

- Production multi-tenant security certification.
- Bypassing host permissions, sandbox restrictions, authentication, or rate limits.
- Autonomous deployment, repository push, or destructive host operations.
- Claims of OpenHands authorship, merged PRs, or benchmark performance without links.
