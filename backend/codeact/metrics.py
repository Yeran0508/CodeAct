from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any


def percentile(samples: list[float], fraction: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


@dataclass(frozen=True)
class EvaluationMetrics:
    tasks: int
    successes: int
    success_rate: float
    duration_total_ms: float
    duration_p50_ms: float
    duration_p95_ms: float
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    retries: int
    timeouts: int
    failure_categories: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize_manifest(manifest: dict[str, Any]) -> EvaluationMetrics:
    records = list(manifest.get("tasks", {}).values())
    durations: list[float] = []
    successes = 0
    input_tokens = 0
    output_tokens = 0
    cache_read_tokens = 0
    cache_write_tokens = 0
    retries = 0
    timeouts = 0
    failures: Counter[str] = Counter()

    for record in records:
        result = record.get("result")
        if record.get("status") != "completed" or not isinstance(result, dict):
            failures["runner_error"] += 1
            continue
        successes += int(bool(result.get("success")))
        duration = float(result.get("duration_ms", 0))
        durations.append(duration)
        retries += int(result.get("retries", 0))
        timeouts += int(result.get("timeouts", 0))
        usage = result.get("usage", {})
        input_tokens += int(usage.get("input_tokens", 0))
        output_tokens += int(usage.get("output_tokens", 0))
        cache_read_tokens += int(usage.get("cache_read_tokens", 0))
        cache_write_tokens += int(usage.get("cache_write_tokens", 0))
        category = result.get("failure_category")
        if category:
            failures[str(category)] += 1

    tasks = len(records)
    return EvaluationMetrics(
        tasks=tasks,
        successes=successes,
        success_rate=successes / tasks if tasks else 0.0,
        duration_total_ms=round(sum(durations), 3),
        duration_p50_ms=round(percentile(durations, 0.50), 3),
        duration_p95_ms=round(percentile(durations, 0.95), 3),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        retries=retries,
        timeouts=timeouts,
        failure_categories=dict(sorted(failures.items())),
    )
