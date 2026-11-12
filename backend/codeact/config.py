from __future__ import annotations

import os
from dataclasses import dataclass


def _positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


@dataclass(frozen=True)
class Settings:
    environment: str = "development"
    max_steps: int = 10
    max_consecutive_failures: int = 3
    execution_timeout_seconds: int = 30
    max_output_chars: int = 12_000
    docker_image: str = "python:3.12.10-slim"
    cpu_limit: str = "1.0"
    memory_limit: str = "512m"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            environment=os.getenv("CODEACT_ENVIRONMENT", "development"),
            max_steps=_positive_int("CODEACT_MAX_STEPS", 10),
            max_consecutive_failures=_positive_int(
                "CODEACT_MAX_CONSECUTIVE_FAILURES", 3
            ),
            execution_timeout_seconds=_positive_int(
                "CODEACT_EXECUTION_TIMEOUT_SECONDS", 30
            ),
            max_output_chars=_positive_int("CODEACT_MAX_OUTPUT_CHARS", 12_000),
            docker_image=os.getenv("CODEACT_DOCKER_IMAGE", "python:3.12.10-slim"),
            cpu_limit=os.getenv("CODEACT_CPU_LIMIT", "1.0"),
            memory_limit=os.getenv("CODEACT_MEMORY_LIMIT", "512m"),
        )
