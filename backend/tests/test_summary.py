import json

from codeact.models import (
    Action,
    CodeLanguage,
    Observation,
    PolicyDecision,
    RiskLevel,
    StepRecord,
)
from codeact.summary import summarize_history


def test_summary_preserves_paths_exact_errors_decisions_and_unresolved_work() -> None:
    history = (
        StepRecord(
            step=1,
            action=Action.execute(
                "from pathlib import Path; Path('src/app.py').write_text('x')",
                CodeLanguage.PYTHON,
            ),
            policy=PolicyDecision(RiskLevel.WRITE, False, ("filesystem write",)),
            observation=Observation(
                "created src/app.py\n",
                "FileNotFoundError: /tmp/config.json\n",
                1,
                8,
            ),
            rolled_back=True,
            approval_id="grant-1",
        ),
    )
    summary = summarize_history(history, unresolved=("add tests for src/app.py",))
    assert summary.paths == ("src/app.py", "/tmp/config.json")
    assert summary.errors[0].stderr == "FileNotFoundError: /tmp/config.json\n"
    assert summary.decisions[0].risk == "write"
    assert summary.decisions[0].reasons == ("filesystem write",)
    assert summary.decisions[0].approval_id == "grant-1"
    assert summary.decisions[0].rolled_back
    assert summary.unresolved == (
        "step 1 failed: exit_code=1",
        "add tests for src/app.py",
    )


def test_summary_is_canonical_deduplicated_and_timeout_aware() -> None:
    history = (
        StepRecord(
            step=2,
            action=Action.execute("cat logs/run.log", CodeLanguage.BASH),
            observation=Observation("logs/run.log", "deadline exceeded", None, 1000, True),
        ),
        StepRecord(step=3, action=Action.finish("inspect logs/run.log")),
    )
    first = summarize_history(history, unresolved=("retry request", "retry request"))
    second = summarize_history(history, unresolved=("retry request", "retry request"))
    assert first == second
    assert first.paths == ("logs/run.log",)
    assert first.unresolved == ("step 2 failed: timed out", "retry request")
    rendered = first.to_prompt()
    assert rendered == second.to_prompt()
    assert json.loads(rendered)["summarized_steps"] == 2
    assert "deadline exceeded" in rendered
