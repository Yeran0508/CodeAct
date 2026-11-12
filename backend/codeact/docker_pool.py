from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from codeact.context import truncate_output
from codeact.models import Action, CodeLanguage, Observation
from codeact.sandbox_pool import SandboxLease, WarmSandboxPool


@dataclass(frozen=True)
class DockerSandboxHandle:
    container_id: str


@dataclass(frozen=True)
class DockerWarmBackend:
    image: str = "python:3.12.10-slim"
    cpu_limit: str = "1.0"
    memory_limit: str = "512m"
    pids_limit: int = 128
    workspace_size: str = "128m"
    command_timeout_seconds: int = 30
    max_output_chars: int = 12_000
    container_user: str | None = None

    def _user(self) -> str:
        if self.container_user:
            return self.container_user
        uid = os.getuid() if hasattr(os, "getuid") else 65534
        gid = os.getgid() if hasattr(os, "getgid") else 65534
        return f"{uid}:{gid}" if uid != 0 else "65534:65534"

    def create(self) -> DockerSandboxHandle:
        user = self._user()
        uid, gid = user.split(":", maxsplit=1)
        command = [
            "docker",
            "run",
            "--detach",
            "--rm",
            "--network",
            "none",
            "--cpus",
            self.cpu_limit,
            "--memory",
            self.memory_limit,
            "--pids-limit",
            str(self.pids_limit),
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--read-only",
            "--user",
            user,
            "--workdir",
            "/workspace",
            "--env",
            "HOME=/tmp",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--tmpfs",
            f"/tmp:rw,nosuid,nodev,size=64m,uid={uid},gid={gid},mode=700",
            "--tmpfs",
            (
                f"/workspace:rw,nosuid,nodev,size={self.workspace_size},"
                f"uid={uid},gid={gid},mode=700"
            ),
            self.image,
            "sleep",
            "infinity",
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=self.command_timeout_seconds,
            check=False,
        )
        container_id = completed.stdout.strip()
        if completed.returncode != 0 or not container_id:
            raise RuntimeError(f"failed to create warm sandbox: {completed.stderr.strip()}")
        return DockerSandboxHandle(container_id)

    def destroy(self, handle: DockerSandboxHandle) -> None:
        subprocess.run(
            ["docker", "rm", "--force", handle.container_id],
            capture_output=True,
            text=True,
            timeout=self.command_timeout_seconds,
            check=False,
        )

    def is_healthy(self, handle: DockerSandboxHandle) -> bool:
        completed = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Running}}",
                handle.container_id,
            ],
            capture_output=True,
            text=True,
            timeout=self.command_timeout_seconds,
            check=False,
        )
        return completed.returncode == 0 and completed.stdout.strip() == "true"

    def execute(self, handle: DockerSandboxHandle, action: Action) -> Observation:
        interpreter = "python" if action.language is CodeLanguage.PYTHON else "bash"
        command = [
            "docker",
            "exec",
            "--workdir",
            "/workspace",
            handle.container_id,
            interpreter,
            "-c",
            action.code,
        ]
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.command_timeout_seconds,
                check=False,
            )
            stdout, stdout_cut = truncate_output(
                completed.stdout, self.max_output_chars // 2
            )
            stderr, stderr_cut = truncate_output(
                completed.stderr, self.max_output_chars // 2
            )
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


class DockerSandboxSession:
    """One lease with persistent in-container state across actions."""

    def __init__(
        self,
        pool: WarmSandboxPool[DockerSandboxHandle],
        backend: DockerWarmBackend,
        *,
        acquire_timeout_seconds: float | None = None,
    ) -> None:
        if pool.backend is not backend:
            raise ValueError("session backend must be the pool backend instance")
        self.backend = backend
        self._lease: SandboxLease[DockerSandboxHandle] = pool.acquire(
            acquire_timeout_seconds
        )

    @property
    def container_id(self) -> str:
        return self._lease.handle.container_id

    def execute(self, action: Action, workspace: Path | None = None) -> Observation:
        return self.backend.execute(self._lease.handle, action)

    def close(self) -> None:
        self._lease.release()

    def __enter__(self) -> DockerSandboxSession:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
