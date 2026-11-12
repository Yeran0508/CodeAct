from __future__ import annotations

import tempfile
from pathlib import Path

from codeact.agent import AgentRuntime
from codeact.executor import DockerExecutor
from codeact.models import Action, CodeLanguage, StopReason


class FailingMutationModel:
    def next_action(self, task, history, last_observation):
        return Action.execute(
            "from pathlib import Path\n"
            "Path('state.txt').write_text('changed')\n"
            "raise RuntimeError('expected failure')",
            CodeLanguage.PYTHON,
        )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="codeact-m1-real-") as directory:
        workspace = Path(directory)
        executor = DockerExecutor(timeout_seconds=10)
        identity = executor.execute(
            Action.execute(
                "from pathlib import Path\n"
                "import os\n"
                "Path('uid.txt').write_text(str(os.getuid()))\n"
                "print(os.getuid())",
                CodeLanguage.PYTHON,
            ),
            workspace,
        )
        if not identity.succeeded or identity.stdout.strip() == "0":
            raise RuntimeError(f"non-root write verification failed: {identity}")
        if (workspace / "uid.txt").read_text() != identity.stdout.strip():
            raise RuntimeError("container write was not visible in the workspace")

        network = executor.execute(
            Action.execute(
                "import socket\nsocket.create_connection(('1.1.1.1', 53), timeout=1)",
                CodeLanguage.PYTHON,
            ),
            workspace,
        )
        if network.succeeded:
            raise RuntimeError("network-disabled container unexpectedly connected")

        (workspace / "state.txt").write_text("original")
        result = AgentRuntime(
            FailingMutationModel(),
            executor,
            max_steps=1,
            max_consecutive_failures=1,
        ).run("rollback failed mutation", workspace)
        if result.stop_reason is not StopReason.FAILURE_LIMIT:
            raise RuntimeError(f"unexpected stop reason: {result.stop_reason}")
        if not result.steps[0].rolled_back:
            raise RuntimeError("failed mutation did not report rollback")
        if (workspace / "state.txt").read_text() != "original":
            raise RuntimeError("failed mutation was not restored")

        print(
            "M1 Docker verification passed:",
            f"uid={identity.stdout.strip()}",
            f"network_exit={network.exit_code}",
            "rollback=true",
        )


if __name__ == "__main__":
    main()
