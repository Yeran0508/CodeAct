from __future__ import annotations

import argparse
import json
import platform
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from codeact.docker_pool import DockerWarmBackend
from codeact.models import Action, CodeLanguage
from codeact.sandbox_pool import WarmSandboxPool


def percentile(samples: list[float], fraction: float) -> float:
    ordered = sorted(samples)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize(samples: list[float]) -> dict[str, float | list[float]]:
    return {
        "samples_ms": [round(sample, 3) for sample in samples],
        "p50_ms": round(percentile(samples, 0.50), 3),
        "p95_ms": round(percentile(samples, 0.95), 3),
        "min_ms": round(min(samples), 3),
        "max_ms": round(max(samples), 3),
    }


def docker_metadata(image: str) -> dict[str, str]:
    version = subprocess.run(
        ["docker", "version", "--format", "{{.Client.Version}}/{{.Server.Version}}"],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    ).stdout.strip()
    digest = subprocess.run(
        ["docker", "image", "inspect", image, "--format", "{{.Id}}"],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    ).stdout.strip()
    return {"docker_client_server": version, "image_id": digest}


def wait_for_capacity(pool: WarmSandboxPool, expected: int) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if pool.stats().available == expected:
            return
        time.sleep(0.01)
    raise RuntimeError("warm pool did not recover before benchmark deadline")


def benchmark(iterations: int, pool_size: int, image: str) -> dict:
    if iterations < 5:
        raise ValueError("iterations must be at least 5")
    if pool_size < 1:
        raise ValueError("pool size must be positive")

    backend = DockerWarmBackend(image=image)
    action = Action.execute("print('ready')", CodeLanguage.PYTHON)
    cold_samples: list[float] = []
    warm_samples: list[float] = []

    for _ in range(iterations):
        handle = None
        started = time.perf_counter()
        try:
            handle = backend.create()
            observation = backend.execute(handle, action)
            if not observation.succeeded or observation.stdout.strip() != "ready":
                raise RuntimeError(f"cold execution failed: {observation}")
            cold_samples.append((time.perf_counter() - started) * 1000)
        finally:
            if handle is not None:
                backend.destroy(handle)

    pool = WarmSandboxPool(backend, size=pool_size, acquire_timeout_seconds=30)
    pool.start()
    try:
        for _ in range(iterations):
            wait_for_capacity(pool, pool_size)
            started = time.perf_counter()
            lease = pool.acquire()
            try:
                observation = backend.execute(lease.handle, action)
                if not observation.succeeded or observation.stdout.strip() != "ready":
                    raise RuntimeError(f"warm execution failed: {observation}")
                warm_samples.append((time.perf_counter() - started) * 1000)
            finally:
                lease.release()
    finally:
        pool.close()

    cold = summarize(cold_samples)
    warm = summarize(warm_samples)
    cold_p50 = float(cold["p50_ms"])
    warm_p50 = float(warm["p50_ms"])
    return {
        "schema_version": 1,
        "recorded_at": datetime.now(UTC).isoformat(),
        "host": platform.platform(),
        "image": image,
        **docker_metadata(image),
        "iterations": iterations,
        "pool_size": pool_size,
        "action": "python -c print('ready')",
        "cold_definition": "create container + exec action",
        "warm_definition": "health-checked pool acquire + exec action; replacement excluded",
        "cold": cold,
        "warm": warm,
        "p50_reduction_percent": round((cold_p50 - warm_p50) / cold_p50 * 100, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark CodeAct cold versus warm execution")
    parser.add_argument("--iterations", type=int, default=12)
    parser.add_argument("--pool-size", type=int, default=2)
    parser.add_argument("--image", default="python:3.12.10-slim")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = benchmark(arguments.iterations, arguments.pool_size, arguments.image)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered)
    print(rendered, end="")


if __name__ == "__main__":
    main()
