import pytest
from codeact.baselines import (
    ActionMode,
    BaselineBudget,
    DeterministicFixtureModel,
    SemanticPlan,
    decode_action,
    encode_action,
)
from codeact.local_benchmark import LocalBenchmarkTask
from codeact.models import Action, CodeLanguage


@pytest.mark.parametrize("mode", list(ActionMode))
def test_action_representations_round_trip(mode: ActionMode) -> None:
    actions = (
        Action.execute("print('你好')", CodeLanguage.PYTHON),
        Action.execute("printf ok", CodeLanguage.BASH),
        Action.finish("done"),
    )
    assert tuple(decode_action(encode_action(action, mode), mode) for action in actions) == actions


def test_same_fixture_model_produces_identical_semantic_actions_under_equal_budgets() -> None:
    task = LocalBenchmarkTask("task", "write result", {}, "print('pass')")
    actions = (Action.execute("print(42)", CodeLanguage.PYTHON),)
    model = DeterministicFixtureModel(
        {"task": SemanticPlan(actions)},
        BaselineBudget(max_actions=2, max_input_tokens=100, max_output_tokens=100),
    )
    code_plan = model.plan(task, ActionMode.CODE_ACTION)
    json_plan = model.plan(task, ActionMode.JSON_TOOL)
    assert code_plan.actions == json_plan.actions == actions
    assert code_plan.answer == json_plan.answer
    assert code_plan.usage.input_tokens == json_plan.usage.input_tokens
    assert code_plan.planning_failure is None
    assert json_plan.planning_failure is None


def test_fixture_model_enforces_equal_step_and_token_budgets() -> None:
    task = LocalBenchmarkTask("task", "instruction", {}, "print('pass')")
    action = Action.execute("print('long output')", CodeLanguage.PYTHON)
    step_model = DeterministicFixtureModel(
        {"task": SemanticPlan((action, action))},
        BaselineBudget(max_actions=1, max_input_tokens=100, max_output_tokens=100),
    )
    assert step_model.plan(task, ActionMode.CODE_ACTION).planning_failure == "step_budget"

    token_model = DeterministicFixtureModel(
        {"task": SemanticPlan((action,))},
        BaselineBudget(max_actions=2, max_input_tokens=1, max_output_tokens=1),
    )
    for mode in ActionMode:
        assert token_model.plan(task, mode).planning_failure in {
            "input_token_budget",
            "output_token_budget",
        }


def test_invalid_baseline_budget_and_response_are_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        BaselineBudget(max_actions=0)
    with pytest.raises(ValueError, match="invalid"):
        decode_action("not-valid", ActionMode.CODE_ACTION)
    with pytest.raises(ValueError, match="unknown"):
        decode_action('{"arguments":{},"tool":"missing"}', ActionMode.JSON_TOOL)
