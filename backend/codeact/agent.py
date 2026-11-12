from __future__ import annotations

from pathlib import Path
from typing import Protocol

from codeact.approval import ApprovalGrant
from codeact.audit import AuditLogger
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
from codeact.prompting import ModelResponse, UsageTracker
from codeact.workspace import WorkspaceManager


class ModelClient(Protocol):
    def next_action(
        self, task: str, history: tuple[StepRecord, ...], last_observation: Observation | None
    ) -> Action | ModelResponse: ...


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
        audit_logger: AuditLogger | None = None,
        usage_tracker: UsageTracker | None = None,
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
        self.audit_logger = audit_logger
        self.usage_tracker = usage_tracker or UsageTracker()

    def run(self, task: str, workspace: Path, *, run_id: str = "local-run") -> RunResult:
        history: list[StepRecord] = []
        last_observation: Observation | None = None
        failures = 0
        if self.audit_logger:
            self.audit_logger.record("run_started", run_id, {"task": task})

        def finish(answer: str, reason: StopReason) -> RunResult:
            result = RunResult(answer, reason, tuple(history))
            if self.audit_logger:
                self.audit_logger.record(
                    "run_finished",
                    run_id,
                    {"answer": answer, "steps": len(history), "stop_reason": reason.value},
                )
            return result

        for step in range(1, self.max_steps + 1):
            proposed = self.model.next_action(task, tuple(history), last_observation)
            if isinstance(proposed, ModelResponse):
                action = proposed.action
                self.usage_tracker.record(proposed.usage)
                if self.audit_logger:
                    self.audit_logger.record(
                        "model_usage",
                        run_id,
                        {
                            "cache_read_tokens": proposed.usage.cache_read_tokens,
                            "cache_write_tokens": proposed.usage.cache_write_tokens,
                            "input_tokens": proposed.usage.input_tokens,
                            "output_tokens": proposed.usage.output_tokens,
                            "step": step,
                        },
                    )
            else:
                action = proposed
            if self.audit_logger:
                self.audit_logger.record(
                    "action_proposed",
                    run_id,
                    {
                        "code": action.code,
                        "kind": action.kind.value,
                        "language": action.language.value,
                        "step": step,
                    },
                )
            if action.kind is ActionKind.FINISH:
                history.append(StepRecord(step=step, action=action))
                return finish(action.answer, StopReason.COMPLETED)

            decision = self.policy.evaluate(action)
            approval = None
            if decision.requires_approval:
                approval = self.approval_gate.authorize(action, decision.reasons)
            if decision.requires_approval and approval is None:
                history.append(StepRecord(step=step, action=action, policy=decision))
                if self.audit_logger:
                    self.audit_logger.record(
                        "approval_denied",
                        run_id,
                        {"reasons": decision.reasons, "step": step},
                    )
                return finish("", StopReason.APPROVAL_DENIED)

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
            if self.audit_logger:
                self.audit_logger.record(
                    "execution_finished",
                    run_id,
                    {
                        "approval_id": approval.grant_id if approval else None,
                        "duration_ms": observation.duration_ms,
                        "exit_code": observation.exit_code,
                        "rolled_back": rolled_back,
                        "stderr": observation.stderr,
                        "stdout": observation.stdout,
                        "step": step,
                        "timed_out": observation.timed_out,
                    },
                )
            last_observation = observation
            failures = 0 if observation.succeeded else failures + 1
            if failures >= self.max_consecutive_failures:
                return finish("", StopReason.FAILURE_LIMIT)
        return finish("", StopReason.MAX_STEPS)
