import os
from pathlib import Path

import pytest
from codeact.agent import AgentRuntime
from codeact.executor import DockerExecutor
from codeact.models import Action, CodeLanguage, StopReason

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("CODEACT_RUN_DOCKER_INTEGRATION") != "1",
        reason="set CODEACT_RUN_DOCKER_INTEGRATION=1 with Docker available",
    ),
]


def test_real_container_is_non_root_can_write_and_has_no_network(tmp_path: Path) -> None:
    identity = DockerExecutor().execute(
        Action.execute(
            "from pathlib import Path\n"
            "import os\n"
            "Path('result.txt').write_text(str(os.getuid()))\n"
            "print(os.getuid())",
            CodeLanguage.PYTHON,
        ),
        tmp_path,
    )
    assert identity.succeeded
    assert identity.stdout.strip() != "0"
    assert (tmp_path / "result.txt").read_text() == identity.stdout.strip()

    network = DockerExecutor().execute(
        Action.execute(
            "import socket\nsocket.create_connection(('1.1.1.1', 53), timeout=1)",
            CodeLanguage.PYTHON,
        ),
        tmp_path,
    )
    assert not network.succeeded


class OneActionModel:
    def next_action(self, task, history, last_observation):
        return Action.execute(
            "from pathlib import Path\n"
            "Path('state.txt').write_text('changed')\n"
            "raise RuntimeError('fail after mutation')",
            CodeLanguage.PYTHON,
        )


def test_real_failed_container_action_rolls_back_workspace(tmp_path: Path) -> None:
    (tmp_path / "state.txt").write_text("original")
    runtime = AgentRuntime(
        OneActionModel(),
        DockerExecutor(),
        max_steps=1,
        max_consecutive_failures=1,
    )
    result = runtime.run("mutate then fail", tmp_path)
    assert result.stop_reason is StopReason.FAILURE_LIMIT
    assert result.steps[0].rolled_back
    assert (tmp_path / "state.txt").read_text() == "original"
