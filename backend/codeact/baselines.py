from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum

from codeact.local_benchmark import CandidatePlan, LocalBenchmarkTask
from codeact.models import Action, ActionKind, CodeLanguage
from codeact.prompting import ProviderUsage

TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


class ActionMode(StrEnum):
    CODE_ACTION = "code_action"
    JSON_TOOL = "json_tool"


@dataclass(frozen=True)
class BaselineBudget:
    max_actions: int = 4
    max_input_tokens: int = 2_000
    max_output_tokens: int = 1_000

    def __post_init__(self) -> None:
        if min(self.max_actions, self.max_input_tokens, self.max_output_tokens) < 1:
            raise ValueError("baseline budgets must be positive")


def count_fixture_tokens(value: str) -> int:
    return len(TOKEN_PATTERN.findall(value))


def encode_action(action: Action, mode: ActionMode) -> str:
    if mode is ActionMode.CODE_ACTION:
        if action.kind is ActionKind.FINISH:
            return f"FINISH\n{action.answer}"
        return f"EXECUTE {action.language.value}\n{action.code}"
    payload = (
        {"tool": "finish", "arguments": {"answer": action.answer}}
        if action.kind is ActionKind.FINISH
        else {
            "tool": "execute_code",
            "arguments": {"code": action.code, "language": action.language.value},
        }
    )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def decode_action(value: str, mode: ActionMode) -> Action:
    if mode is ActionMode.CODE_ACTION:
        header, separator, body = value.partition("\n")
        if not separator:
            raise ValueError("invalid code-action response")
        if header == "FINISH":
            return Action.finish(body)
        prefix, separator, language = header.partition(" ")
        if prefix != "EXECUTE" or not separator:
            raise ValueError("invalid code-action header")
        return Action.execute(body, CodeLanguage(language))
    payload = json.loads(value)
    tool = payload.get("tool")
    arguments = payload.get("arguments")
    if not isinstance(arguments, dict):
        raise ValueError("JSON tool arguments must be an object")
    if tool == "finish":
        return Action.finish(arguments["answer"])
    if tool == "execute_code":
        return Action.execute(arguments["code"], CodeLanguage(arguments["language"]))
    raise ValueError("unknown JSON tool")


@dataclass(frozen=True)
class SemanticPlan:
    actions: tuple[Action, ...]
    answer: str = "completed"


class DeterministicFixtureModel:
    """One semantic planner rendered through two action representations."""

    model_id = "deterministic-fixture-model-v1"
    seed = 20261112

    def __init__(self, plans: dict[str, SemanticPlan], budget: BaselineBudget) -> None:
        self.plans = plans
        self.budget = budget

    @staticmethod
    def prompt(task: LocalBenchmarkTask) -> str:
        return json.dumps(
            {"instruction": task.instruction, "task_id": task.task_id},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    def plan(self, task: LocalBenchmarkTask, mode: ActionMode) -> CandidatePlan:
        semantic = self.plans[task.task_id]
        prompt_tokens = count_fixture_tokens(self.prompt(task))
        encoded = [encode_action(action, mode) for action in semantic.actions]
        encoded.append(encode_action(Action.finish(semantic.answer), mode))
        output_tokens = sum(count_fixture_tokens(response) for response in encoded)
        usage = ProviderUsage(prompt_tokens, output_tokens)
        failure = None
        if len(semantic.actions) > self.budget.max_actions:
            failure = "step_budget"
        elif prompt_tokens > self.budget.max_input_tokens:
            failure = "input_token_budget"
        elif output_tokens > self.budget.max_output_tokens:
            failure = "output_token_budget"
        try:
            decoded = tuple(decode_action(response, mode) for response in encoded)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return CandidatePlan((), "", usage, retries=1, planning_failure="parse_error")
        if decoded[-1].kind is not ActionKind.FINISH:
            return CandidatePlan((), "", usage, retries=1, planning_failure="parse_error")
        return CandidatePlan(
            decoded[:-1],
            decoded[-1].answer,
            usage,
            planning_failure=failure,
        )
