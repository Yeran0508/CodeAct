from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EvaluationTask:
    task_id: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.task_id:
            raise ValueError("task ID is required")

    @property
    def digest(self) -> str:
        encoded = json.dumps(
            self.payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class EvaluationRunnerConfig:
    manifest_path: Path
    workspace_root: Path
    max_workers: int = 4

    def __post_init__(self) -> None:
        if self.max_workers < 1:
            raise ValueError("max workers must be positive")


class ManifestMismatchError(ValueError):
    pass


TaskWorker = Callable[[EvaluationTask, Path], Mapping[str, Any]]


class ParallelEvaluationRunner:
    """Parallel, crash-resumable task runner with one clean workspace per attempt."""

    def __init__(
        self,
        config: EvaluationRunnerConfig,
        worker: TaskWorker,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config
        self.worker = worker
        self.clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()
        self._manifest: dict[str, Any] = {}

    def _timestamp(self) -> str:
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError("evaluation timestamps must be timezone-aware")
        return value.isoformat()

    def _workspace(self, task_id: str) -> Path:
        digest = hashlib.sha256(task_id.encode()).hexdigest()
        return self.config.workspace_root / digest

    def _initial_manifest(self, tasks: Sequence[EvaluationTask]) -> dict[str, Any]:
        created_at = self._timestamp()
        return {
            "schema_version": 1,
            "created_at": created_at,
            "updated_at": created_at,
            "tasks": {
                task.task_id: {
                    "attempts": 0,
                    "error": None,
                    "finished_at": None,
                    "payload_digest": task.digest,
                    "result": None,
                    "started_at": None,
                    "status": "pending",
                    "workspace": str(self._workspace(task.task_id)),
                }
                for task in tasks
            },
        }

    def _load_or_create(self, tasks: Sequence[EvaluationTask]) -> None:
        path = self.config.manifest_path
        if path.exists():
            self._manifest = json.loads(path.read_text())
            records = self._manifest.get("tasks", {})
            expected = {task.task_id: task.digest for task in tasks}
            actual = {
                task_id: record.get("payload_digest") for task_id, record in records.items()
            }
            if actual != expected:
                raise ManifestMismatchError("task IDs or payloads do not match the manifest")
            for record in records.values():
                if record["status"] == "running":
                    record["status"] = "pending"
        else:
            self._manifest = self._initial_manifest(tasks)
        self._save_locked()

    def _save_locked(self) -> None:
        path = self.config.manifest_path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._manifest["updated_at"] = self._timestamp()
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(self._manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        os.replace(temporary, path)

    def _prepare_workspace(self, task: EvaluationTask) -> Path:
        workspace = self._workspace(task.task_id)
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True)
        return workspace

    def _execute(self, task: EvaluationTask) -> None:
        with self._lock:
            record = self._manifest["tasks"][task.task_id]
            record["attempts"] += 1
            record["error"] = None
            record["finished_at"] = None
            record["result"] = None
            record["started_at"] = self._timestamp()
            record["status"] = "running"
            self._save_locked()

        try:
            workspace = self._prepare_workspace(task)
            result = dict(self.worker(task, workspace))
        except Exception as error:
            with self._lock:
                record = self._manifest["tasks"][task.task_id]
                record["error"] = f"{type(error).__name__}: {error}"
                record["finished_at"] = self._timestamp()
                record["status"] = "failed"
                self._save_locked()
            return

        with self._lock:
            record = self._manifest["tasks"][task.task_id]
            record["finished_at"] = self._timestamp()
            record["result"] = result
            record["status"] = "completed"
            self._save_locked()

    def run(self, tasks: Sequence[EvaluationTask]) -> dict[str, Any]:
        if not tasks:
            raise ValueError("at least one evaluation task is required")
        if len({task.task_id for task in tasks}) != len(tasks):
            raise ValueError("evaluation task IDs must be unique")
        ordered = tuple(sorted(tasks, key=lambda task: task.task_id))
        with self._lock:
            self._load_or_create(ordered)
            pending = [
                task
                for task in ordered
                if self._manifest["tasks"][task.task_id]["status"] != "completed"
            ]
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            futures = [executor.submit(self._execute, task) for task in pending]
            for future in as_completed(futures):
                future.result()
        with self._lock:
            return json.loads(json.dumps(self._manifest))
