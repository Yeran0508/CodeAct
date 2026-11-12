from pathlib import Path
from unittest.mock import patch

from codeact.executor import DockerExecutor
from codeact.models import Action, CodeLanguage


def test_docker_executor_enforces_isolation_flags(tmp_path: Path) -> None:
    action = Action.execute("print('ok')", CodeLanguage.PYTHON)
    with patch("codeact.executor.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = "ok\n"
        run.return_value.stderr = ""
        result = DockerExecutor().execute(action, tmp_path)
    command = run.call_args.args[0]
    assert command[:3] == ["docker", "run", "--rm"]
    assert command[command.index("--network") + 1] == "none"
    assert "ALL" in command
    assert "no-new-privileges" in command
    assert result.succeeded


def test_docker_executor_truncates_streams(tmp_path: Path) -> None:
    with patch("codeact.executor.subprocess.run") as run:
        run.return_value.returncode = 2
        run.return_value.stdout = "a" * 100
        run.return_value.stderr = "b" * 100
        result = DockerExecutor(max_output_chars=80).execute(
            Action.execute("bad", CodeLanguage.BASH), tmp_path
        )
    assert not result.succeeded
    assert result.truncated_chars > 0
