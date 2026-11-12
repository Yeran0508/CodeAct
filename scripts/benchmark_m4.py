from __future__ import annotations

import argparse
import json
import platform
import re
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from codeact.context import truncate_text
from codeact.models import (
    Action,
    CodeLanguage,
    Observation,
    PolicyDecision,
    RiskLevel,
    StepRecord,
)
from codeact.prompting import PromptBuilder, ProviderUsage, UsageTracker

TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


class FixtureProvider:
    """Deterministic local provider fixture with explicit token and prefix-cache semantics."""

    def __init__(self) -> None:
        self.cached_prefixes: set[str] = set()

    @staticmethod
    def count_tokens(value: str) -> int:
        return len(TOKEN_PATTERN.findall(value))

    def report_usage(self, prefix_hash: str, prefix: str, dynamic: str) -> ProviderUsage:
        prefix_tokens = self.count_tokens(prefix)
        input_tokens = prefix_tokens + self.count_tokens(dynamic)
        if prefix_hash in self.cached_prefixes:
            cache_read = prefix_tokens
            cache_write = 0
        else:
            self.cached_prefixes.add(prefix_hash)
            cache_read = 0
            cache_write = prefix_tokens
        return ProviderUsage(input_tokens, 1, cache_read, cache_write)


def make_case(case_id: int) -> tuple[str, tuple[StepRecord, ...], tuple[str, ...]]:
    critical_path = f"src/module_{case_id}.py"
    exact_error = f"ExactError-{case_id}: dependency mismatch"
    decision = f"decision-{case_id}-requires-review"
    unresolved = f"unresolved-{case_id}-rerun-tests"
    records: list[StepRecord] = []
    for step in range(1, 9):
        if step == 4:
            records.append(
                StepRecord(
                    step=step,
                    action=Action.execute(
                        f"from pathlib import Path; Path('{critical_path}').write_text('x')",
                        CodeLanguage.PYTHON,
                    ),
                    policy=PolicyDecision(RiskLevel.WRITE, True, (decision,)),
                    observation=Observation("", exact_error, 1, 5),
                    rolled_back=True,
                    approval_id=f"grant-{case_id}",
                )
            )
        else:
            noise = " ".join(
                f"noise-{case_id}-{step}-{item}" for item in range(100)
            )
            records.append(
                StepRecord(
                    step=step,
                    action=Action.execute(f"print('{noise}')", CodeLanguage.PYTHON),
                    observation=Observation(noise, "", 0, 1),
                )
            )
    return (
        f"repair case {case_id}",
        tuple(records),
        (critical_path, exact_error, decision, unresolved),
    )


def render_without_summary(
    task: str,
    history: tuple[StepRecord, ...],
    unresolved: str,
    budget: int,
) -> str:
    raw = canonical_json(
        {
            "history": [asdict(record) for record in history],
            "task": task,
            "unresolved": [unresolved],
        }
    )
    return truncate_text(raw, budget).text


def run_mode(summary_enabled: bool, cases: int, budget: int) -> dict:
    builder = PromptBuilder(recent_steps=2)
    provider = FixtureProvider()
    tracker = UsageTracker()
    results = []
    for case_id in range(1, cases + 1):
        task, history, facts = make_case(case_id)
        if summary_enabled:
            envelope = builder.build(task, history, history[-1].observation, unresolved=(facts[3],))
            dynamic = truncate_text(envelope.dynamic_context, budget).text
        else:
            envelope = builder.build(task, (), None)
            dynamic = render_without_summary(task, history, facts[3], budget)
        usage = provider.report_usage(
            envelope.prefix_sha256,
            envelope.stable_prefix,
            dynamic,
        )
        tracker.record(usage)
        retained = {fact: fact in dynamic for fact in facts}
        results.append(
            {
                "case_id": case_id,
                "dynamic_chars": len(dynamic),
                "facts_retained": retained,
                "success": all(retained.values()),
                "usage": asdict(usage),
            }
        )
    totals = tracker.snapshot()
    return {
        "summary_enabled": summary_enabled,
        "successes": sum(result["success"] for result in results),
        "cases": cases,
        "quality_rate": sum(result["success"] for result in results) / cases,
        "dynamic_chars": sum(result["dynamic_chars"] for result in results),
        "usage": asdict(totals),
        "results": results,
        "prefix_sha256": builder.prefix_sha256,
    }


def benchmark(cases: int, budget: int) -> dict:
    if cases < 1:
        raise ValueError("cases must be positive")
    if budget < 1:
        raise ValueError("budget must be positive")
    without_summary = run_mode(False, cases, budget)
    with_summary = run_mode(True, cases, budget)
    return {
        "schema_version": 1,
        "recorded_at": datetime.now(UTC).isoformat(),
        "host": platform.platform(),
        "fixture_provider": "regex-token-provider-v1",
        "token_pattern": TOKEN_PATTERN.pattern,
        "dynamic_character_budget": budget,
        "quality_definition": "all required path/error/decision/unresolved facts retained",
        "without_summary": without_summary,
        "with_summary": with_summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare long-context summary off versus on")
    parser.add_argument("--cases", type=int, default=10)
    parser.add_argument("--budget", type=int, default=2400)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = benchmark(arguments.cases, arguments.budget)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered)
    print(rendered, end="")


if __name__ == "__main__":
    main()
