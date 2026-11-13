from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from codeact.docker_pool import DockerSandboxSession, DockerWarmBackend
from codeact.models import Action, CodeLanguage, Observation
from codeact.prompting import ProviderUsage
from codeact.sandbox_pool import WarmSandboxPool

EVALUATOR_MARKER = "CODEACT_EVALUATOR_PASS"


@dataclass(frozen=True)
class LocalBenchmarkTask:
    task_id: str
    instruction: str
    setup_files: dict[str, str]
    evaluator_python: str


@dataclass(frozen=True)
class CandidatePlan:
    actions: tuple[Action, ...]
    answer: str
    usage: ProviderUsage
    retries: int = 0
    planning_failure: str | None = None


def _validate_relative_path(value: str) -> None:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not value or value.endswith("/"):
        raise ValueError(f"invalid benchmark file path: {value}")


def load_local_dataset(path: Path) -> tuple[LocalBenchmarkTask, ...]:
    document = json.loads(path.read_text())
    if document.get("schema_version") != 1:
        raise ValueError("unsupported local benchmark schema")
    raw_tasks = document.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ValueError("local benchmark requires a non-empty task list")
    tasks: list[LocalBenchmarkTask] = []
    for raw in raw_tasks:
        task_id = raw.get("task_id")
        instruction = raw.get("instruction")
        evaluator = raw.get("evaluator_python")
        setup_files = raw.get("setup_files")
        if not all(isinstance(value, str) and value for value in (task_id, instruction, evaluator)):
            raise ValueError("task ID, instruction, and evaluator are required strings")
        if not isinstance(setup_files, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in setup_files.items()
        ):
            raise ValueError("setup_files must map paths to text")
        for relative_path in setup_files:
            _validate_relative_path(relative_path)
        tasks.append(LocalBenchmarkTask(task_id, instruction, setup_files, evaluator))
    if len({task.task_id for task in tasks}) != len(tasks):
        raise ValueError("local benchmark task IDs must be unique")
    return tuple(tasks)


def evaluation_payload(task: LocalBenchmarkTask) -> dict[str, Any]:
    return asdict(task)


def _setup_action(task: LocalBenchmarkTask) -> Action:
    serialized = json.dumps(task.setup_files, ensure_ascii=False, sort_keys=True)
    code = (
        "import json\n"
        "from pathlib import Path\n"
        f"files = json.loads({serialized!r})\n"
        "for relative, contents in files.items():\n"
        "    path = Path(relative)\n"
        "    path.parent.mkdir(parents=True, exist_ok=True)\n"
        "    path.write_text(contents)\n"
    )
    return Action.execute(code, CodeLanguage.PYTHON)


def _failure_category(observation: Observation) -> str:
    if observation.timed_out:
        return "timeout"
    return "candidate_execution" if observation.exit_code else "infrastructure"


class LocalBenchmarkHarness:
    def __init__(
        self,
        pool: WarmSandboxPool,
        backend: DockerWarmBackend,
        *,
        max_actions: int = 4,
    ) -> None:
        if max_actions < 1:
            raise ValueError("max actions must be positive")
        self.pool = pool
        self.backend = backend
        self.max_actions = max_actions

    def evaluate(
        self,
        task: LocalBenchmarkTask,
        plan: CandidatePlan,
        *,
        mode: str,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        if plan.planning_failure:
            return self._result(
                task,
                plan,
                mode,
                False,
                0,
                plan.planning_failure,
                0,
                started,
            )
        if len(plan.actions) > self.max_actions:
            return self._result(
                task,
                plan,
                mode,
                False,
                0,
                "step_budget",
                0,
                started,
            )
        with DockerSandboxSession(self.pool, self.backend) as session:
            setup = session.execute(_setup_action(task))
            if not setup.succeeded:
                return self._result(
                    task, plan, mode, False, 0, "infrastructure", 0, started
                )
            timeouts = 0
            for index, action in enumerate(plan.actions, start=1):
                observation = session.execute(action)
                timeouts += int(observation.timed_out)
                if not observation.succeeded:
                    return self._result(
                        task,
                        plan,
                        mode,
                        False,
                        index,
                        _failure_category(observation),
                        timeouts,
                        started,
                    )
            evaluator = session.execute(
                Action.execute(task.evaluator_python, CodeLanguage.PYTHON)
            )
            timeouts += int(evaluator.timed_out)
            success = evaluator.succeeded and EVALUATOR_MARKER in evaluator.stdout
            category = None if success else (
                "timeout" if evaluator.timed_out else "evaluator_failure"
            )
            return self._result(
                task,
                plan,
                mode,
                success,
                len(plan.actions),
                category,
                timeouts,
                started,
            )

    @staticmethod
    def _result(
        task: LocalBenchmarkTask,
        plan: CandidatePlan,
        mode: str,
        success: bool,
        actions_attempted: int,
        failure_category: str | None,
        timeouts: int,
        started: float,
    ) -> dict[str, Any]:
        return {
            "task_id": task.task_id,
            "mode": mode,
            "success": success,
            "answer": plan.answer,
            "actions_attempted": actions_attempted,
            "retries": plan.retries,
            "timeouts": timeouts,
            "failure_category": failure_category,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "usage": asdict(plan.usage),
        }
