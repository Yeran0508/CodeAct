from __future__ import annotations

from pathlib import Path
from typing import Protocol

from codeact.executor import Executor
from codeact.models import (
    Action,
    ActionKind,
    Observation,
    RunResult,
    StepRecord,
    StopReason,
)
from codeact.policy import ActionPolicy


class ModelClient(Protocol):
    def next_action(
        self, task: str, history: tuple[StepRecord, ...], last_observation: Observation | None
    ) -> Action: ...


class ApprovalGate(Protocol):
    def approve(self, action: Action, reasons: tuple[str, ...]) -> bool: ...


class DenyByDefault:
    def approve(self, action: Action, reasons: tuple[str, ...]) -> bool:
        return False


class AgentRuntime:
    def __init__(
        self,
        model: ModelClient,
        executor: Executor,
        *,
        policy: ActionPolicy | None = None,
        approval_gate: ApprovalGate | None = None,
        max_steps: int = 10,
        max_consecutive_failures: int = 3,
    ) -> None:
        if max_steps < 1 or max_consecutive_failures < 1:
            raise ValueError("step and failure limits must be positive")
        self.model = model
        self.executor = executor
        self.policy = policy or ActionPolicy()
        self.approval_gate = approval_gate or DenyByDefault()
        self.max_steps = max_steps
        self.max_consecutive_failures = max_consecutive_failures

    def run(self, task: str, workspace: Path) -> RunResult:
        history: list[StepRecord] = []
        last_observation: Observation | None = None
        failures = 0
        for step in range(1, self.max_steps + 1):
            action = self.model.next_action(task, tuple(history), last_observation)
            if action.kind is ActionKind.FINISH:
                history.append(StepRecord(step=step, action=action))
                return RunResult(action.answer, StopReason.COMPLETED, tuple(history))

            decision = self.policy.evaluate(action)
            if decision.requires_approval and not self.approval_gate.approve(
                action, decision.reasons
            ):
                history.append(StepRecord(step=step, action=action, policy=decision))
                return RunResult("", StopReason.APPROVAL_DENIED, tuple(history))

            observation = self.executor.execute(action, workspace)
            history.append(
                StepRecord(
                    step=step,
                    action=action,
                    policy=decision,
                    observation=observation,
                )
            )
            last_observation = observation
            failures = 0 if observation.succeeded else failures + 1
            if failures >= self.max_consecutive_failures:
                return RunResult("", StopReason.FAILURE_LIMIT, tuple(history))
        return RunResult("", StopReason.MAX_STEPS, tuple(history))
