from __future__ import annotations

from dataclasses import dataclass

from codeact.mcp.models import McpTool
from codeact.models import PolicyDecision, RiskLevel


@dataclass(frozen=True)
class McpToolRule:
    risk: RiskLevel
    reasons: tuple[str, ...] = ()


class McpToolPolicy:
    """Host-owned MCP rules; server annotations may elevate but never lower risk."""

    def __init__(self, rules: dict[str, McpToolRule] | None = None) -> None:
        self._rules = rules or {}

    def evaluate(self, server_id: str, tool: McpTool) -> PolicyDecision:
        key = f"{server_id}:{tool.name}"
        rule = self._rules.get(
            key,
            McpToolRule(RiskLevel.HIGH_RISK, ("unclassified MCP tool",)),
        )
        reasons = set(rule.reasons)
        risk = rule.risk
        if tool.annotations.get("destructiveHint") is True:
            risk = RiskLevel.HIGH_RISK
            reasons.add("server marks tool as destructive")
        if tool.annotations.get("openWorldHint") is True:
            risk = RiskLevel.HIGH_RISK
            reasons.add("tool may interact with external systems")
        if risk is RiskLevel.WRITE and not reasons:
            reasons.add("MCP tool mutates state")
        if risk is RiskLevel.HIGH_RISK and not reasons:
            reasons.add("high-risk MCP tool")
        return PolicyDecision(
            risk=risk,
            requires_approval=risk is not RiskLevel.READ_ONLY,
            reasons=tuple(sorted(reasons)),
        )
