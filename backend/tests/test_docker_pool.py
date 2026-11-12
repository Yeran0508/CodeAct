import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from codeact.docker_pool import (
    DockerSandboxHandle,
    DockerSandboxSession,
    DockerWarmBackend,
)
from codeact.models import Action, CodeLanguage
from codeact.sandbox_pool import WarmSandboxPool


def completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def test_backend_creates_hardened_non_root_warm_container() -> None:
    backend = DockerWarmBackend(container_user="1000:1000")
    with patch(
        "codeact.docker_pool.subprocess.run",
        return_value=completed("container-1\n"),
    ) as run:
        handle = backend.create()
    command = run.call_args.args[0]
    assert handle == DockerSandboxHandle("container-1")
    assert command[:3] == ["docker", "run", "--detach"]
    assert command[command.index("--network") + 1] == "none"
    assert command[command.index("--user") + 1] == "1000:1000"
    assert "--read-only" in command
    assert "ALL" in command
    assert "no-new-privileges" in command
    assert "/workspace:rw,nosuid,nodev,size=128m,uid=1000,gid=1000,mode=700" in command


def test_backend_health_destroy_and_execute() -> None:
    backend = DockerWarmBackend()
    handle = DockerSandboxHandle("container-1")
    responses = [
        completed("true\n"),
        completed("4\n"),
        completed(),
    ]
    with patch("codeact.docker_pool.subprocess.run", side_effect=responses) as run:
        assert backend.is_healthy(handle)
        observation = backend.execute(
            handle, Action.execute("print(2 + 2)", CodeLanguage.PYTHON)
        )
        backend.destroy(handle)
    assert observation.succeeded
    assert observation.stdout == "4\n"
    assert run.call_args_list[1].args[0][:4] == [
        "docker",
        "exec",
        "--workdir",
        "/workspace",
    ]
    assert run.call_args_list[2].args[0] == [
        "docker",
        "rm",
        "--force",
        "container-1",
    ]


def test_backend_create_failure_and_execution_timeout() -> None:
    backend = DockerWarmBackend(max_output_chars=40)
    with patch(
        "codeact.docker_pool.subprocess.run",
        return_value=completed("", "image missing", 1),
    ):
        with pytest.raises(RuntimeError, match="image missing"):
            backend.create()
    error = subprocess.TimeoutExpired(
        ["docker"], 1, output=b"a" * 50, stderr=b"b" * 50
    )
    with patch("codeact.docker_pool.subprocess.run", side_effect=error):
        result = backend.execute(
            DockerSandboxHandle("container-1"),
            Action.execute("sleep 60", CodeLanguage.BASH),
        )
    assert result.timed_out
    assert result.exit_code is None
    assert result.truncated_chars > 0


class SessionBackend:
    def __init__(self) -> None:
        self.next_id = 1
        self.destroyed = []
        self.actions = []

    def create(self):
        handle = DockerSandboxHandle(f"container-{self.next_id}")
        self.next_id += 1
        return handle

    def destroy(self, handle):
        self.destroyed.append(handle)

    def is_healthy(self, handle):
        return True

    def execute(self, handle, action):
        self.actions.append((handle, action))
        return completed("ok")


def test_session_uses_one_container_for_multiple_steps_then_destroys() -> None:
    backend = SessionBackend()
    pool = WarmSandboxPool(backend, size=1)
    pool.start()
    with DockerSandboxSession(pool, backend) as session:
        container_id = session.container_id
        session.execute(Action.execute("x = 1", CodeLanguage.PYTHON), Path("."))
        session.execute(Action.execute("print(x)", CodeLanguage.PYTHON))
        assert [item[0].container_id for item in backend.actions] == [
            container_id,
            container_id,
        ]
    assert backend.destroyed[0].container_id == container_id
    pool.close()


def test_session_requires_same_backend_instance() -> None:
    backend = SessionBackend()
    pool = WarmSandboxPool(backend, size=1)
    pool.start()
    with pytest.raises(ValueError, match="pool backend"):
        DockerSandboxSession(pool, SessionBackend())
    pool.close()
