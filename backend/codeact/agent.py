from __future__ import annotations

from pathlib import Path
from typing import Protocol

from codeact.approval import ApprovalGrant
from codeact.executor import Executor
from codeact.models import (
    Action,
    ActionKind,
    Observation,
    RiskLevel,
    RunResult,
    StepRecord,
    StopReason,
)
from codeact.policy import ActionPolicy
from codeact.workspace import WorkspaceManager


class ModelClient(Protocol):
    def next_action(
        self, task: str, history: tuple[StepRecord, ...], last_observation: Observation | None
    ) -> Action: ...


class ApprovalGate(Protocol):
    def authorize(self, action: Action, reasons: tuple[str, ...]) -> ApprovalGrant | None: ...


class DenyByDefault:
    def authorize(self, action: Action, reasons: tuple[str, ...]) -> ApprovalGrant | None:
        return None


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
        workspace_manager: WorkspaceManager | None = None,
    ) -> None:
        if max_steps < 1 or max_consecutive_failures < 1:
            raise ValueError("step and failure limits must be positive")
        self.model = model
        self.executor = executor
        self.policy = policy or ActionPolicy()
        self.approval_gate = approval_gate or DenyByDefault()
        self.max_steps = max_steps
        self.max_consecutive_failures = max_consecutive_failures
        self.workspace_manager = workspace_manager

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
            approval = None
            if decision.requires_approval:
                approval = self.approval_gate.authorize(action, decision.reasons)
            if decision.requires_approval and approval is None:
                history.append(StepRecord(step=step, action=action, policy=decision))
                return RunResult("", StopReason.APPROVAL_DENIED, tuple(history))

            snapshot = None
            if decision.risk is not RiskLevel.READ_ONLY:
                manager = self.workspace_manager or WorkspaceManager(workspace.parent)
                snapshot = manager.snapshot(workspace)
            observation = self.executor.execute(action, workspace)
            rolled_back = False
            if snapshot is not None:
                if not observation.succeeded:
                    snapshot.restore()
                    rolled_back = True
                snapshot.close()
            history.append(
                StepRecord(
                    step=step,
                    action=action,
                    policy=decision,
                    observation=observation,
                    rolled_back=rolled_back,
                    approval_id=approval.grant_id if approval else None,
                )
            )
            last_observation = observation
            failures = 0 if observation.succeeded else failures + 1
            if failures >= self.max_consecutive_failures:
                return RunResult("", StopReason.FAILURE_LIMIT, tuple(history))
        return RunResult("", StopReason.MAX_STEPS, tuple(history))
