# M3 cold-versus-warm Docker benchmark - 2026-11-12

## Question

How much latency does an already-created CodeAct sandbox save for the first trivial action compared
with creating a new container for that action?

## Environment

- Host: macOS 15.3.1 x86_64, Docker Desktop
- Docker client/server: 27.4.0 / 27.4.0
- Image: `python:3.12.10-slim`
- Image ID: `sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db`
- Base commit before the benchmark module: `a5e78125556071275302406cbbcb5701f0e98da2`
- Action: `python -c "print('ready')"`
- Samples: 12 cold and 12 warm, sequential, pool size 2
- Raw manifest: `docs/experiments/results/m3-warm-pool-benchmark.json`

No language model, dataset, decoding, token budget, or evaluator is involved in this infrastructure
microbenchmark.

## Definitions

- Cold latency starts immediately before `docker run --detach` and ends after the action result.
- Warm latency starts immediately before pool acquisition, includes the health inspection and
  action, and ends after the action result.
- Initial pool creation and post-lease asynchronous replacement are excluded from warm latency.
- Container destruction is excluded from both timed regions.
- P50 and P95 use linear interpolation over sorted samples.

## Reproduction

~~~bash
PYTHONPATH=backend:. python3 scripts/benchmark_m3.py \
  --iterations 12 \
  --pool-size 2 \
  --output docs/experiments/results/m3-warm-pool-benchmark.json
~~~

## Result

| Mode | P50 | P95 | Min | Max |
| --- | ---: | ---: | ---: | ---: |
| Cold create + execute | 701.654 ms | 935.908 ms | 498.207 ms | 988.875 ms |
| Warm acquire + execute | 241.200 ms | 297.220 ms | 198.779 ms | 302.901 ms |

Warm acquisition reduced P50 by 65.62% in this run.

## Limitations

This is one local run with a cached image and a trivial action, not a general Docker performance
claim. Docker Desktop VM load, host load, image size, action duration, pool contention, and health
check cost can change the result. The benchmark deliberately measures request-path latency and does
not hide the compute cost of replacement; replacement occurs outside the request path.
