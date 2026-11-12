import json

import pytest
from codeact.models import Action, CodeLanguage, Observation, StepRecord
from codeact.prompting import PromptBuilder, ProviderUsage, UsageTracker


def test_prompt_prefix_is_stable_while_dynamic_context_changes() -> None:
    builder = PromptBuilder(recent_steps=1)
    first = builder.build("task-a", (), None)
    history = (
        StepRecord(
            step=1,
            action=Action.execute("cat src/app.py", CodeLanguage.BASH),
            observation=Observation("ok", "", 0, 1),
        ),
        StepRecord(
            step=2,
            action=Action.execute("pytest", CodeLanguage.BASH),
            observation=Observation("", "failure", 1, 2),
        ),
    )
    second = builder.build("task-b", history, history[-1].observation)
    assert first.stable_prefix == second.stable_prefix
    assert first.prefix_sha256 == second.prefix_sha256
    assert first.dynamic_context != second.dynamic_context
    payload = json.loads(second.dynamic_context)
    assert json.loads(payload["history_summary"])["paths"] == ["src/app.py"]
    assert payload["recent_steps"][0]["step"] == 2


def test_prompt_builder_validates_recent_step_count() -> None:
    with pytest.raises(ValueError, match="recent"):
        PromptBuilder(recent_steps=-1)


def test_usage_tracker_accumulates_provider_reported_cache_tokens() -> None:
    tracker = UsageTracker()
    tracker.record(ProviderUsage(100, 20, cache_read_tokens=60, cache_write_tokens=10))
    tracker.record(ProviderUsage(80, 10, cache_read_tokens=40))
    snapshot = tracker.snapshot()
    assert snapshot.calls == 2
    assert snapshot.input_tokens == 180
    assert snapshot.output_tokens == 30
    assert snapshot.cache_read_tokens == 100
    assert snapshot.cache_write_tokens == 10
    assert snapshot.cache_read_fraction == pytest.approx(100 / 180)


def test_provider_usage_rejects_impossible_counts() -> None:
    with pytest.raises(ValueError, match="negative"):
        ProviderUsage(-1, 0)
    with pytest.raises(ValueError, match="exceed"):
        ProviderUsage(10, 1, cache_read_tokens=11)
