import json
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from codeact.evaluation import (
    EvaluationRunnerConfig,
    EvaluationTask,
    ManifestMismatchError,
    ParallelEvaluationRunner,
)


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 11, 12, tzinfo=UTC)
        self.lock = threading.Lock()

    def __call__(self) -> datetime:
        with self.lock:
            self.value += timedelta(milliseconds=1)
            return self.value


def config(tmp_path: Path, max_workers: int = 2) -> EvaluationRunnerConfig:
    return EvaluationRunnerConfig(
        manifest_path=tmp_path / "manifest.json",
        workspace_root=tmp_path / "workspaces",
        max_workers=max_workers,
    )


def test_runner_parallelizes_with_distinct_clean_workspaces(tmp_path: Path) -> None:
    active = 0
    maximum = 0
    lock = threading.Lock()
    workspaces: set[Path] = set()

    def worker(task, workspace):
        nonlocal active, maximum
        assert not any(workspace.iterdir())
        with lock:
            workspaces.add(workspace)
            active += 1
            maximum = max(maximum, active)
        (workspace / "marker.txt").write_text(task.task_id)
        time.sleep(0.02)
        with lock:
            active -= 1
        return {"success": True, "task_id": task.task_id}

    tasks = [EvaluationTask(f"task-{index}", {"value": index}) for index in range(4)]
    runner = ParallelEvaluationRunner(config(tmp_path), worker, clock=Clock())
    manifest = runner.run(tasks)
    assert maximum == 2
    assert len(workspaces) == 4
    assert all(record["status"] == "completed" for record in manifest["tasks"].values())
    assert json.loads((tmp_path / "manifest.json").read_text()) == manifest


def test_runner_resumes_only_incomplete_tasks_and_cleans_retry_workspace(
    tmp_path: Path,
) -> None:
    calls: dict[str, int] = {}

    def worker(task, workspace):
        calls[task.task_id] = calls.get(task.task_id, 0) + 1
        if task.task_id == "flaky" and calls[task.task_id] == 1:
            (workspace / "dirty.txt").write_text("must disappear")
            raise RuntimeError("interrupted")
        assert not (workspace / "dirty.txt").exists()
        return {"success": True}

    tasks = [EvaluationTask("done", {}), EvaluationTask("flaky", {})]
    runner = ParallelEvaluationRunner(config(tmp_path), worker, clock=Clock())
    first = runner.run(tasks)
    assert first["tasks"]["done"]["status"] == "completed"
    assert first["tasks"]["flaky"]["status"] == "failed"

    second = ParallelEvaluationRunner(config(tmp_path), worker, clock=Clock()).run(tasks)
    assert calls == {"done": 1, "flaky": 2}
    assert second["tasks"]["flaky"]["attempts"] == 2
    assert second["tasks"]["flaky"]["status"] == "completed"


def test_runner_validates_tasks_manifest_and_configuration(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="workers"):
        config(tmp_path, 0)
    runner = ParallelEvaluationRunner(config(tmp_path), lambda task, workspace: {})
    with pytest.raises(ValueError, match="at least"):
        runner.run([])
    with pytest.raises(ValueError, match="unique"):
        runner.run([EvaluationTask("same", {}), EvaluationTask("same", {})])
    runner.run([EvaluationTask("task", {"version": 1})])
    with pytest.raises(ManifestMismatchError, match="payload"):
        ParallelEvaluationRunner(config(tmp_path), lambda task, workspace: {}).run(
            [EvaluationTask("task", {"version": 2})]
        )
    with pytest.raises(ValueError, match="task ID"):
        EvaluationTask("", {})


def test_runner_recovers_records_left_running_by_a_crash(tmp_path: Path) -> None:
    task = EvaluationTask("task", {})
    runner = ParallelEvaluationRunner(config(tmp_path), lambda item, workspace: {"success": True})
    runner.run([task])
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    manifest["tasks"]["task"]["status"] = "running"
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    resumed = ParallelEvaluationRunner(
        config(tmp_path), lambda item, workspace: {"success": True}
    ).run([task])
    assert resumed["tasks"]["task"]["attempts"] == 2
    assert resumed["tasks"]["task"]["status"] == "completed"
