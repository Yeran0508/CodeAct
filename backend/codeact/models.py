from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class CodeLanguage(StrEnum):
    PYTHON = "python"
    BASH = "bash"


class ActionKind(StrEnum):
    EXECUTE = "execute"
    FINISH = "finish"


class RiskLevel(StrEnum):
    READ_ONLY = "read_only"
    WRITE = "write"
    HIGH_RISK = "high_risk"


class StopReason(StrEnum):
    COMPLETED = "completed"
    MAX_STEPS = "max_steps"
    FAILURE_LIMIT = "failure_limit"
    APPROVAL_DENIED = "approval_denied"


@dataclass(frozen=True)
class Action:
    kind: ActionKind
    code: str = ""
    language: CodeLanguage = CodeLanguage.PYTHON
    answer: str = ""

    @classmethod
    def execute(cls, code: str, language: CodeLanguage) -> Action:
        return cls(kind=ActionKind.EXECUTE, code=code, language=language)

    @classmethod
    def finish(cls, answer: str) -> Action:
        return cls(kind=ActionKind.FINISH, answer=answer)


@dataclass(frozen=True)
class PolicyDecision:
    risk: RiskLevel
    requires_approval: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class Observation:
    stdout: str
    stderr: str
    exit_code: int | None
    duration_ms: int
    timed_out: bool = False
    truncated_chars: int = 0

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


@dataclass(frozen=True)
class StepRecord:
    step: int
    action: Action
    policy: PolicyDecision | None = None
    observation: Observation | None = None
    rolled_back: bool = False


@dataclass(frozen=True)
class RunResult:
    answer: str
    stop_reason: StopReason
    steps: tuple[StepRecord, ...] = field(default_factory=tuple)
