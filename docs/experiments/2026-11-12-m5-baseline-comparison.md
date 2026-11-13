# M5 equal-budget local baseline comparison - 2026-11-12

## Scope

This experiment validates the end-to-end comparison harness and representation accounting. It does
not compare production language-model quality.

## Reproducibility record

- Git base commit: `b12344eda621e5e119d89034bfee0f8d942fba9c`
- Host: macOS 15.3.1 x86_64
- Docker client/server: 27.4.0 / 27.4.0
- Image: `python:3.12.10-slim`
- Image ID: `sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db`
- Dataset: `benchmarks/codeact-local-v1.json`
- Dataset SHA-256: `a65ae233bdf11347dd0a406c67dc1d040d6c3efe920dfa7ff150176929cdb5e6`
- Task IDs: `csv-maximum`, `inventory-total`, `nested-report`, `normalize-words`,
  `stateful-two-step`, `sum-integers`
- Model: `deterministic-fixture-model-v1`, seed `20261112`, deterministic decoding
- Modes: Code-action and canonical JSON-tool; only action serialization changes
- Budgets: 4 actions, 2,000 input tokens, 1,000 output tokens, 30 seconds per command
- Workers/pool: 3 / 3
- Cache: disabled
- Network: none
- Approval: not applicable to trusted fixture plans
- Evaluator: identical trusted in-container assertions and pass marker
- Raw files: `m5-code_action-manifest.json`, `m5-json_tool-manifest.json`, and
  `m5-baseline-comparison.json` under `docs/experiments/results/`

## Reproduction

~~~bash
PYTHONPATH=backend:. python3 scripts/benchmark_m5.py \
  --fresh \
  --output-directory docs/experiments/results
~~~

Without `--fresh`, completed manifest records are resumed and skipped.

## Results

| Metric | Code-action | JSON-tool |
| --- | ---: | ---: |
| Success | 6/6 | 6/6 |
| Input tokens | 216 | 216 |
| Output tokens | 353 | 696 |
| Cache read/write | 0 / 0 | 0 / 0 |
| Retries | 0 | 0 |
| Timeouts | 0 | 0 |
| Failure categories | none | none |
| Duration P50 | 1457.869 ms | 2084.628 ms |
| Duration P95 | 2047.665 ms | 2735.625 ms |
| Duration total | 9152.670 ms | 12778.329 ms |

Both codecs round-tripped to identical typed actions, so equal success is expected for this
deterministic fixture. JSON-tool serialization used 343 more fixture output tokens (97.17% more)
for these exact plans.

## Limitations and unsupported claims

The token counts come from the documented local regex fixture, not a production provider. Modes ran
sequentially on Docker Desktop, so latency differences can reflect VM and host load and must not be
attributed to representation. Six deterministic tasks cannot establish model-quality superiority.
No OpenHands contribution, production security certification, production-provider cache result, or
SWE-bench score is claimed.

SWE-bench remains gated on installing and validating its official harness, exact image set, dataset
revision, model/provider configuration, credentials, cost controls, and evaluator. This repository
does not substitute its local evaluator for that harness.
