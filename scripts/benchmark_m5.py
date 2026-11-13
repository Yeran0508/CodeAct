from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from codeact.baselines import (
    ActionMode,
    BaselineBudget,
    DeterministicFixtureModel,
    SemanticPlan,
)
from codeact.docker_pool import DockerWarmBackend
from codeact.evaluation import (
    EvaluationRunnerConfig,
    EvaluationTask,
    ParallelEvaluationRunner,
)
from codeact.local_benchmark import (
    EVALUATOR_MARKER,
    LocalBenchmarkHarness,
    evaluation_payload,
    load_local_dataset,
)
from codeact.metrics import summarize_manifest
from codeact.sandbox_pool import WarmSandboxPool

from scripts.verify_m5_local import PLANS


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def environment_metadata(image: str) -> dict[str, str]:
    docker_version = subprocess.run(
        ["docker", "version", "--format", "{{.Client.Version}}/{{.Server.Version}}"],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    ).stdout.strip()
    image_id = subprocess.run(
        ["docker", "image", "inspect", image, "--format", "{{.Id}}"],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    ).stdout.strip()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    ).stdout.strip()
    return {
        "host": platform.platform(),
        "docker_client_server": docker_version,
        "image_id": image_id,
        "git_commit": commit,
    }


def run_comparison(
    dataset_path: Path,
    output_directory: Path,
    *,
    fresh: bool,
) -> dict:
    image = "python:3.12.10-slim"
    tasks = load_local_dataset(dataset_path)
    task_by_id = {task.task_id: task for task in tasks}
    semantic_plans = {
        task_id: SemanticPlan(actions) for task_id, actions in PLANS.items()
    }
    budget = BaselineBudget(
        max_actions=4,
        max_input_tokens=2_000,
        max_output_tokens=1_000,
    )
    model = DeterministicFixtureModel(semantic_plans, budget)
    backend = DockerWarmBackend(image=image, command_timeout_seconds=30)
    pool = WarmSandboxPool(backend, size=3, acquire_timeout_seconds=30)
    output_directory.mkdir(parents=True, exist_ok=True)
    workspace_root = Path(".codeact-m5-workspaces")
    if fresh:
        for mode in ActionMode:
            manifest_path = output_directory / f"m5-{mode.value}-manifest.json"
            if manifest_path.exists():
                manifest_path.unlink()
        if workspace_root.exists():
            shutil.rmtree(workspace_root)

    manifests: dict[str, dict] = {}
    pool.start()
    try:
        harness = LocalBenchmarkHarness(pool, backend, max_actions=budget.max_actions)
        evaluation_tasks = [
            EvaluationTask(task.task_id, evaluation_payload(task)) for task in tasks
        ]
        for mode in ActionMode:
            config = EvaluationRunnerConfig(
                manifest_path=output_directory / f"m5-{mode.value}-manifest.json",
                workspace_root=workspace_root / mode.value,
                max_workers=3,
            )

            def worker(item: EvaluationTask, workspace: Path, selected=mode):
                task = task_by_id[item.task_id]
                plan = model.plan(task, selected)
                return harness.evaluate(task, plan, mode=selected.value)

            manifests[mode.value] = ParallelEvaluationRunner(config, worker).run(
                evaluation_tasks
            )
    finally:
        pool.close()
        if workspace_root.exists():
            shutil.rmtree(workspace_root)

    comparison = {
        mode: summarize_manifest(manifest).to_dict()
        for mode, manifest in manifests.items()
    }
    return {
        "schema_version": 1,
        "recorded_at": datetime.now(UTC).isoformat(),
        **environment_metadata(image),
        "image": image,
        "dataset": str(dataset_path),
        "dataset_sha256": file_sha256(dataset_path),
        "task_ids": sorted(task.task_id for task in tasks),
        "model": {
            "id": model.model_id,
            "seed": model.seed,
            "decoding": "deterministic semantic fixture",
            "context_limit": budget.max_input_tokens,
            "cache_behavior": "disabled",
        },
        "budget": {
            **asdict(budget),
            "command_timeout_seconds": backend.command_timeout_seconds,
            "workers": 3,
            "pool_size": 3,
        },
        "evaluator": {
            "type": "trusted in-container assertions",
            "pass_marker": EVALUATOR_MARKER,
        },
        "approval_policy": "not applicable: trusted deterministic fixture plans",
        "network_policy": "none",
        "comparison": comparison,
        "unsupported_claims": [
            "No production language-model quality conclusion",
            "No production-provider token or cache conclusion",
            "No SWE-bench or OpenHands result",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run equal-budget local M5 baselines")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("benchmarks/codeact-local-v1.json"),
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("docs/experiments/results"),
    )
    parser.add_argument("--fresh", action="store_true")
    arguments = parser.parse_args()
    result = run_comparison(
        arguments.dataset,
        arguments.output_directory,
        fresh=arguments.fresh,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    result_path = arguments.output_directory / "m5-baseline-comparison.json"
    result_path.write_text(rendered)
    print(rendered, end="")


if __name__ == "__main__":
    main()
