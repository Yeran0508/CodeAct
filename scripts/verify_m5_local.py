from __future__ import annotations

import tempfile
from pathlib import Path

from codeact.docker_pool import DockerWarmBackend
from codeact.evaluation import (
    EvaluationRunnerConfig,
    EvaluationTask,
    ParallelEvaluationRunner,
)
from codeact.local_benchmark import (
    CandidatePlan,
    LocalBenchmarkHarness,
    evaluation_payload,
    load_local_dataset,
)
from codeact.models import Action, CodeLanguage
from codeact.prompting import ProviderUsage
from codeact.sandbox_pool import WarmSandboxPool


def action(code: str) -> Action:
    return Action.execute(code, CodeLanguage.PYTHON)


PLANS = {
    "sum-integers": (
        action(
            "from pathlib import Path\n"
            "p = Path('numbers.txt')\n"
            "Path('result.txt').write_text(str(sum(map(int, p.read_text().split()))))"
        ),
    ),
    "normalize-words": (
        action(
            "from pathlib import Path\n"
            "words = Path('words.txt').read_text().lower().split()\n"
            "Path('result.txt').write_text('\\n'.join(sorted(set(words))) + '\\n')"
        ),
    ),
    "inventory-total": (
        action(
            "import json\nfrom pathlib import Path\n"
            "data = json.loads(Path('inventory.json').read_text())\n"
            "Path('result.txt').write_text(str(sum(item['qty'] for item in data)))"
        ),
    ),
    "csv-maximum": (
        action(
            "import csv\nfrom pathlib import Path\n"
            "rows = list(csv.DictReader(Path('scores.csv').open()))\n"
            "best = max(rows, key=lambda row: int(row['score']))\n"
            "Path('result.txt').write_text(best['name'])"
        ),
    ),
    "nested-report": (
        action(
            "from pathlib import Path\n"
            "path = Path('output/report.txt')\n"
            "path.parent.mkdir()\npath.write_text('READY\\n')"
        ),
    ),
    "stateful-two-step": (
        action(
            "from pathlib import Path\n"
            "value = int(Path('seed.txt').read_text()) * 2\n"
            "Path('intermediate.txt').write_text(str(value))"
        ),
        action(
            "from pathlib import Path\n"
            "value = Path('intermediate.txt').read_text()\n"
            "Path('result.txt').write_text(value)"
        ),
    ),
}


def main() -> None:
    tasks = load_local_dataset(Path("benchmarks/codeact-local-v1.json"))
    by_id = {task.task_id: task for task in tasks}
    backend = DockerWarmBackend()
    pool = WarmSandboxPool(backend, size=2, acquire_timeout_seconds=20)
    pool.start()
    try:
        harness = LocalBenchmarkHarness(pool, backend, max_actions=4)
        with tempfile.TemporaryDirectory(prefix="codeact-m5-local-") as directory:
            root = Path(directory)
            config = EvaluationRunnerConfig(
                manifest_path=root / "manifest.json",
                workspace_root=root / "workspaces",
                max_workers=2,
            )

            def worker(item: EvaluationTask, workspace: Path):
                task = by_id[item.task_id]
                plan = CandidatePlan(
                    PLANS[item.task_id],
                    "completed",
                    ProviderUsage(0, 0),
                )
                return harness.evaluate(task, plan, mode="code_action")

            evaluation_tasks = [
                EvaluationTask(task.task_id, evaluation_payload(task)) for task in tasks
            ]
            first = ParallelEvaluationRunner(config, worker).run(evaluation_tasks)
            second = ParallelEvaluationRunner(config, worker).run(evaluation_tasks)
            records = first["tasks"].values()
            if not all(
                record["status"] == "completed" and record["result"]["success"]
                for record in records
            ):
                raise RuntimeError("local Docker benchmark acceptance failed")
            if not all(record["attempts"] == 1 for record in second["tasks"].values()):
                raise RuntimeError("resume unexpectedly reran completed tasks")
    finally:
        pool.close()

    print(
        "M5 local Docker benchmark verification passed:",
        f"tasks={len(tasks)}",
        "workers=2",
        "clean_sandbox_per_task=true",
        "resume_skipped=6",
    )


if __name__ == "__main__":
    main()
