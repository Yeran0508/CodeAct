from pathlib import Path

from codeact.agent import AgentRuntime
from codeact.models import Action, CodeLanguage, Observation, StopReason


class ScriptedModel:
    def __init__(self, actions: list[Action]) -> None:
        self.actions = iter(actions)
        self.observations: list[Observation | None] = []

    def next_action(self, task, history, last_observation):
        self.observations.append(last_observation)
        return next(self.actions)


class FakeExecutor:
    def __init__(self, observations: list[Observation]) -> None:
        self.observations = iter(observations)
        self.calls = 0

    def execute(self, action, workspace):
        self.calls += 1
        return next(self.observations)


class ApproveAll:
    def approve(self, action, reasons):
        return True


def observation(exit_code: int = 0) -> Observation:
    return Observation("result", "", exit_code, 1)


def test_runtime_returns_observation_to_model_then_finishes(tmp_path: Path) -> None:
    model = ScriptedModel(
        [Action.execute("print(2 + 2)", CodeLanguage.PYTHON), Action.finish("4")]
    )
    runtime = AgentRuntime(model, FakeExecutor([observation()]))
    result = runtime.run("calculate", tmp_path)
    assert result.stop_reason is StopReason.COMPLETED
    assert result.answer == "4"
    assert model.observations[1] == observation()
    assert len(result.steps) == 2


def test_runtime_denies_high_risk_action_by_default(tmp_path: Path) -> None:
    executor = FakeExecutor([])
    model = ScriptedModel([Action.execute("rm -rf data", CodeLanguage.BASH)])
    result = AgentRuntime(model, executor).run("delete data", tmp_path)
    assert result.stop_reason is StopReason.APPROVAL_DENIED
    assert executor.calls == 0


def test_runtime_can_execute_approved_action(tmp_path: Path) -> None:
    executor = FakeExecutor([observation()])
    model = ScriptedModel(
        [Action.execute("rm file.txt", CodeLanguage.BASH), Action.finish("done")]
    )
    result = AgentRuntime(model, executor, approval_gate=ApproveAll()).run("task", tmp_path)
    assert result.stop_reason is StopReason.COMPLETED
    assert executor.calls == 1


def test_runtime_stops_after_consecutive_failures(tmp_path: Path) -> None:
    model = ScriptedModel(
        [
            Action.execute("bad1", CodeLanguage.PYTHON),
            Action.execute("bad2", CodeLanguage.PYTHON),
        ]
    )
    runtime = AgentRuntime(
        model, FakeExecutor([observation(1), observation(1)]), max_consecutive_failures=2
    )
    assert runtime.run("task", tmp_path).stop_reason is StopReason.FAILURE_LIMIT


def test_runtime_stops_at_step_budget(tmp_path: Path) -> None:
    model = ScriptedModel([Action.execute("1", CodeLanguage.PYTHON)])
    runtime = AgentRuntime(model, FakeExecutor([observation()]), max_steps=1)
    assert runtime.run("task", tmp_path).stop_reason is StopReason.MAX_STEPS
