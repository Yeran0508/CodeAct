# M5 local Docker harness acceptance - 2026-11-12

## Scope

This acceptance validates the representation-neutral local dataset, parallel runner, one clean
Docker sandbox per task, evaluator lifecycle, and resume behavior. It is not a model benchmark.

## Environment

- Host: macOS 15.3.1, Docker Desktop 27.4.0
- Base commit before M5-B: `05bce6e`
- Image: `python:3.12.10-slim`
- Dataset: `benchmarks/codeact-local-v1.json`, schema version 1
- Exact task IDs: `csv-maximum`, `inventory-total`, `nested-report`, `normalize-words`,
  `stateful-two-step`, `sum-integers`
- Tasks/workers/pool size: 6 / 2 / 2
- Network policy: Docker network `none`
- Action budget: 4 candidate actions per task

## Reproduction

~~~bash
PYTHONPATH=backend python3 scripts/verify_m5_local.py
~~~

## Result

All six fixed candidate plans passed their trusted evaluators. The stateful task used two actions in
one lease. Every task released and destroyed its container, the pool supplied clean replacements,
and a second run over the same manifest skipped all six completed records with attempts remaining
at one.

## Limitations

Candidate plans are deterministic fixtures and report zero tokens; this checks harness mechanics,
not model quality. The equal-budget Code-action/JSON-tool comparison and metric report belong to
M5-C/M5-D. No SWE-bench result is claimed.
