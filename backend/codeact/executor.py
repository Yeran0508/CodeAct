from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from codeact.context import truncate_output
from codeact.models import Action, CodeLanguage, Observation


class Executor(Protocol):
    def execute(self, action: Action, workspace: Path) -> Observation: ...


@dataclass(frozen=True)
class DockerExecutor:
    """Run one action in a disposable, network-disabled Docker container."""

    image: str = "python:3.12.10-slim"
    timeout_seconds: int = 30
    max_output_chars: int = 12_000
    cpu_limit: str = "1.0"
    memory_limit: str = "512m"

    def execute(self, action: Action, workspace: Path) -> Observation:
        workspace = workspace.resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        interpreter = "python" if action.language is CodeLanguage.PYTHON else "bash"
        flag = "-c"
        command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--cpus",
            self.cpu_limit,
            "--memory",
            self.memory_limit,
            "--pids-limit",
            "128",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            "65534:65534",
            "--workdir",
            "/workspace",
            "--mount",
            f"type=bind,src={workspace},dst=/workspace",
            self.image,
            interpreter,
            flag,
            action.code,
        ]
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            stdout, stdout_cut = truncate_output(completed.stdout, self.max_output_chars // 2)
            stderr, stderr_cut = truncate_output(completed.stderr, self.max_output_chars // 2)
            return Observation(
                stdout=stdout,
                stderr=stderr,
                exit_code=completed.returncode,
                duration_ms=int((time.monotonic() - started) * 1000),
                truncated_chars=stdout_cut + stderr_cut,
            )
        except subprocess.TimeoutExpired as error:
            stdout = error.stdout or ""
            stderr = error.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode(errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode(errors="replace")
            stdout, stdout_cut = truncate_output(stdout, self.max_output_chars // 2)
            stderr, stderr_cut = truncate_output(stderr, self.max_output_chars // 2)
            return Observation(
                stdout=stdout,
                stderr=stderr,
                exit_code=None,
                duration_ms=int((time.monotonic() - started) * 1000),
                timed_out=True,
                truncated_chars=stdout_cut + stderr_cut,
            )
