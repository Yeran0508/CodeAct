# CodeAct Runtime

CodeAct Runtime is a from-scratch educational agent execution framework inspired by the ICML
2024 CodeAct paper. A model proposes Python or Bash as an action; the runtime evaluates policy,
executes accepted code in a disposable Docker container, and returns bounded output and errors so
the model can correct its next step.

## Current status

M0 is implemented as a testable library baseline:

- typed Python/Bash actions, observations, step records, and terminal results;
- model-action-policy-execution-observation loop;
- completion, maximum-step, consecutive-failure, and denied-approval stop conditions;
- deny-by-default approval for statically detected high-risk behavior;
- disposable Docker execution with networking disabled, resource limits, non-root UID, dropped
  capabilities, no-new-privileges, timeouts, and output truncation;
- Python 3.12 packaging, Docker test image, Ruff/pytest/coverage gates, and CI.

This checkpoint does not claim an MCP connection, warm container pool, snapshot rollback,
SWE-bench result, model-quality improvement, or OpenHands contribution. Those are evidence-gated
milestones in requirements.md.

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

Tests mock the Docker process boundary while asserting required isolation flags. A real Docker
integration test and workspace rollback arrive in M1. Until then, do not run arbitrary untrusted
code with this repository.

## Documents

- [V1 requirements and evidence rules](requirements.md)
- [Architecture and trust boundaries](docs/architecture.md)
- [Runtime contract](docs/api-contract.md)
- [Experiment protocol](docs/experiments/README.md)
- [Chinese learning notes](CodeAct学习笔记.txt)
