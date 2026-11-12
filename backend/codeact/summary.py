from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from codeact.models import StepRecord

PATH_PATTERN = re.compile(
    r"(?<![\w.-])(?:/[\w.@%+~/-]+|(?:[\w.@%+~-]+/)+[\w.@%+~-]+|"
    r"[\w.@%+~-]+\.[A-Za-z0-9]{1,8})(?![\w.-])"
)


@dataclass(frozen=True)
class DecisionRecord:
    step: int
    risk: str | None
    reasons: tuple[str, ...]
    approval_id: str | None
    rolled_back: bool
    exit_code: int | None
    timed_out: bool


@dataclass(frozen=True)
class ErrorRecord:
    step: int
    stderr: str


@dataclass(frozen=True)
class HistorySummary:
    paths: tuple[str, ...]
    errors: tuple[ErrorRecord, ...]
    decisions: tuple[DecisionRecord, ...]
    unresolved: tuple[str, ...]
    summarized_steps: int

    def to_prompt(self) -> str:
        """Render canonical structured data without paraphrasing critical facts."""
        return json.dumps(
            asdict(self),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


def _unique_in_order(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def summarize_history(
    history: tuple[StepRecord, ...],
    *,
    unresolved: tuple[str, ...] = (),
) -> HistorySummary:
    paths: list[str] = []
    errors: list[ErrorRecord] = []
    decisions: list[DecisionRecord] = []
    inferred_unresolved: list[str] = []

    for record in history:
        evidence = [record.action.code, record.action.answer]
        if record.observation:
            evidence.extend([record.observation.stdout, record.observation.stderr])
            if record.observation.stderr:
                errors.append(ErrorRecord(record.step, record.observation.stderr))
            if not record.observation.succeeded:
                failure = f"step {record.step} failed"
                if record.observation.timed_out:
                    failure += ": timed out"
                else:
                    failure += f": exit_code={record.observation.exit_code}"
                inferred_unresolved.append(failure)
        for text in evidence:
            paths.extend(match.group(0) for match in PATH_PATTERN.finditer(text))

        policy = record.policy
        material_decision = (
            policy is not None
            or record.approval_id is not None
            or record.rolled_back
            or (record.observation is not None and not record.observation.succeeded)
        )
        if material_decision:
            decisions.append(
                DecisionRecord(
                    step=record.step,
                    risk=policy.risk.value if policy else None,
                    reasons=policy.reasons if policy else (),
                    approval_id=record.approval_id,
                    rolled_back=record.rolled_back,
                    exit_code=record.observation.exit_code if record.observation else None,
                    timed_out=record.observation.timed_out if record.observation else False,
                )
            )

    return HistorySummary(
        paths=_unique_in_order(paths),
        errors=tuple(errors),
        decisions=tuple(decisions),
        unresolved=_unique_in_order([*inferred_unresolved, *unresolved]),
        summarized_steps=len(history),
    )
