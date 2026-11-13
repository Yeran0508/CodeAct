import json
from pathlib import Path

import pytest
from codeact.local_benchmark import (
    CandidatePlan,
    LocalBenchmarkHarness,
    LocalBenchmarkTask,
    evaluation_payload,
    load_local_dataset,
)
from codeact.models import Action, CodeLanguage, Observation
from codeact.prompting import ProviderUsage


def write_dataset(path: Path, tasks: list[dict]) -> None:
    path.write_text(json.dumps({"schema_version": 1, "tasks": tasks}))


def test_dataset_loader_validates_schema_paths_and_unique_ids(tmp_path: Path) -> None:
    valid = {
        "task_id": "task",
        "instruction": "do work",
        "setup_files": {"input/data.txt": "value"},
        "evaluator_python": "print('CODEACT_EVALUATOR_PASS')",
    }
    path = tmp_path / "dataset.json"
    write_dataset(path, [valid])
    task = load_local_dataset(path)[0]
    assert task.task_id == "task"
    assert evaluation_payload(task)["setup_files"] == {"input/data.txt": "value"}

    write_dataset(path, [{**valid, "setup_files": {"../secret": "x"}}])
    with pytest.raises(ValueError, match="path"):
        load_local_dataset(path)
    write_dataset(path, [valid, valid])
    with pytest.raises(ValueError, match="unique"):
        load_local_dataset(path)


class FakeBackend:
    def __init__(self, observations: list[Observation]) -> None:
        self.observations = iter(observations)
        self.next_id = 0
        self.destroyed = []

    def create(self):
        from codeact.docker_pool import DockerSandboxHandle

        self.next_id += 1
        return DockerSandboxHandle(f"container-{self.next_id}")

    def destroy(self, handle):
        self.destroyed.append(handle)

    def is_healthy(self, handle):
        return True

    def execute(self, handle, action):
        return next(self.observations)


def test_harness_reports_success_failure_and_step_budget() -> None:
    from codeact.sandbox_pool import WarmSandboxPool

    task = LocalBenchmarkTask("task", "do work", {}, "print('pass')")
    action = Action.execute("print('candidate')", CodeLanguage.PYTHON)
    plan = CandidatePlan((action,), "done", ProviderUsage(10, 2), retries=1)
    backend = FakeBackend(
        [
            Observation("", "", 0, 1),
            Observation("", "", 0, 2),
            Observation("CODEACT_EVALUATOR_PASS", "", 0, 1),
        ]
    )
    pool = WarmSandboxPool(backend, size=1)
    pool.start()
    result = LocalBenchmarkHarness(pool, backend).evaluate(task, plan, mode="code_action")
    assert result["success"]
    assert result["actions_attempted"] == 1
    assert result["retries"] == 1
    assert result["usage"]["input_tokens"] == 10
    pool.close()

    limited = LocalBenchmarkHarness(pool, backend, max_actions=1)
    over_budget = CandidatePlan((action, action), "", ProviderUsage(1, 1))
    limited_result = limited.evaluate(task, over_budget, mode="code_action")
    assert limited_result["failure_category"] == "step_budget"


def test_harness_classifies_candidate_timeout() -> None:
    from codeact.sandbox_pool import WarmSandboxPool

    backend = FakeBackend(
        [Observation("", "", 0, 1), Observation("", "", None, 100, timed_out=True)]
    )
    pool = WarmSandboxPool(backend, size=1)
    pool.start()
    plan = CandidatePlan(
        (Action.execute("sleep 10", CodeLanguage.BASH),),
        "",
        ProviderUsage(2, 1),
    )
    result = LocalBenchmarkHarness(pool, backend).evaluate(
        LocalBenchmarkTask("task", "timeout", {}, "print('pass')"),
        plan,
        mode="code_action",
    )
    assert not result["success"]
    assert result["timeouts"] == 1
    assert result["failure_category"] == "timeout"
    pool.close()
