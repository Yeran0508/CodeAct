from __future__ import annotations

import json
import subprocess
import time

from codeact.docker_pool import DockerSandboxSession, DockerWarmBackend
from codeact.models import Action, CodeLanguage
from codeact.sandbox_pool import WarmSandboxPool


def wait_for_capacity(pool: WarmSandboxPool, expected: int) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if pool.stats().available == expected:
            return
        time.sleep(0.05)
    raise RuntimeError(f"pool did not recover to {expected} available containers")


def inspect_container(container_id: str) -> dict:
    completed = subprocess.run(
        ["docker", "inspect", container_id],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    return json.loads(completed.stdout)[0]


def main() -> None:
    backend = DockerWarmBackend()
    pool = WarmSandboxPool(backend, size=2, acquire_timeout_seconds=10)
    first_id = ""
    second_id = ""
    pool.start()
    try:
        with DockerSandboxSession(pool, backend) as first:
            first_id = first.container_id
            state = inspect_container(first_id)
            host = state["HostConfig"]
            if host["NetworkMode"] != "none" or not host["ReadonlyRootfs"]:
                raise RuntimeError("container network or root filesystem isolation is incorrect")
            if host["PidsLimit"] != backend.pids_limit or host["Memory"] <= 0:
                raise RuntimeError("container PID or memory limits are missing")
            if "ALL" not in host["CapDrop"]:
                raise RuntimeError("container capabilities were not dropped")

            written = first.execute(
                Action.execute(
                    "from pathlib import Path; Path('secret.txt').write_text('session-one')",
                    CodeLanguage.PYTHON,
                )
            )
            visible = first.execute(
                Action.execute(
                    "from pathlib import Path; print(Path('secret.txt').read_text())",
                    CodeLanguage.PYTHON,
                )
            )
            if not written.succeeded or visible.stdout.strip() != "session-one":
                raise RuntimeError("state was not preserved inside one session")

        wait_for_capacity(pool, 2)
        with DockerSandboxSession(pool, backend) as second:
            second_id = second.container_id
            leaked = second.execute(
                Action.execute(
                    "from pathlib import Path; print(Path('secret.txt').exists())",
                    CodeLanguage.PYTHON,
                )
            )
            if not leaked.succeeded or leaked.stdout.strip() != "False":
                raise RuntimeError("workspace state leaked across sessions")
            if second_id == first_id:
                raise RuntimeError("a dirty container was reused")
    finally:
        pool.close()

    print(
        "M3 Docker isolation verification passed:",
        "pool_size=2",
        "same_session_state=true",
        "cross_session_leak=false",
        "resource_limits=true",
        f"containers={first_id[:12]},{second_id[:12]}",
    )


if __name__ == "__main__":
    main()
