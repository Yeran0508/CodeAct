from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from codeact.approval import ApprovalGrant, BoundApprovalGate
from codeact.mcp.client import McpClient, McpToolValidationError
from codeact.mcp.models import McpTool, tool_call_digest
from codeact.mcp.policy import McpToolPolicy, McpToolRule
from codeact.models import RiskLevel

NOW = datetime(2026, 11, 12, 15, 0, tzinfo=UTC)


class CallTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def request(self, method, params):
        self.calls.append((method, dict(params)))
        return {"content": [{"type": "text", "text": "ok"}]}

    def notify(self, method, params=None):
        pass

    def close(self):
        pass


def client_with_tool(tool: McpTool) -> tuple[McpClient, CallTransport]:
    transport = CallTransport()
    client = McpClient(transport, server_id="fixture")
    client.server_info = {"connected": True}
    client.tools = {tool.name: tool}
    return client, transport


def test_read_only_tool_validates_and_calls_without_approval() -> None:
    tool = McpTool(
        "read_note",
        "Read a note",
        {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
    )
    client, transport = client_with_tool(tool)
    policy = McpToolPolicy(
        {"fixture:read_note": McpToolRule(RiskLevel.READ_ONLY)}
    )
    outcome = client.call_tool("read_note", {"name": "intro"}, policy=policy)
    assert outcome.result.content[0]["text"] == "ok"
    assert outcome.approval_id is None
    assert transport.calls == [
        ("tools/call", {"name": "read_note", "arguments": {"name": "intro"}})
    ]


def test_invalid_arguments_and_unknown_tool_never_reach_transport() -> None:
    tool = McpTool(
        "sum_values",
        "",
        {
            "type": "object",
            "properties": {"values": {"type": "array", "items": {"type": "number"}}},
            "required": ["values"],
        },
    )
    client, transport = client_with_tool(tool)
    with pytest.raises(McpToolValidationError, match="values"):
        client.call_tool("sum_values", {"values": ["bad"]}, policy=McpToolPolicy())
    with pytest.raises(KeyError, match="not discovered"):
        client.call_tool("missing", {}, policy=McpToolPolicy())
    assert transport.calls == []


def test_unclassified_tool_requires_exact_single_use_approval() -> None:
    tool = McpTool("write_note", "", {"type": "object"})
    client, transport = client_with_tool(tool)
    arguments = {"text": "hello"}
    digest = tool_call_digest("fixture", "write_note", arguments)
    reasons = ("unclassified MCP tool",)
    grant = ApprovalGrant.issue_for_digest(
        digest,
        reasons,
        approver="reviewer",
        ttl=timedelta(minutes=5),
        now=NOW,
    )
    gate = BoundApprovalGate([grant], clock=lambda: NOW)
    outcome = client.call_tool(
        "write_note",
        arguments,
        policy=McpToolPolicy(),
        approval_gate=gate,
    )
    assert outcome.result.content[0]["text"] == "ok"
    assert outcome.approval_id == grant.grant_id
    with pytest.raises(PermissionError, match="approval required"):
        client.call_tool(
            "write_note",
            arguments,
            policy=McpToolPolicy(),
            approval_gate=gate,
        )
    assert len(transport.calls) == 1


def test_changed_arguments_do_not_match_grant() -> None:
    tool = McpTool("write_note", "", {"type": "object"})
    client, transport = client_with_tool(tool)
    grant = ApprovalGrant.issue_for_digest(
        tool_call_digest("fixture", "write_note", {"text": "approved"}),
        ("unclassified MCP tool",),
        approver="reviewer",
        ttl=timedelta(minutes=5),
        now=NOW,
    )
    with pytest.raises(PermissionError, match="approval required"):
        client.call_tool(
            "write_note",
            {"text": "changed"},
            policy=McpToolPolicy(),
            approval_gate=BoundApprovalGate([grant], clock=lambda: NOW),
        )
    assert transport.calls == []


def test_server_annotations_can_only_elevate_host_rule() -> None:
    destructive = McpTool(
        "read_note",
        "",
        {"type": "object"},
        {"readOnlyHint": True, "destructiveHint": True, "openWorldHint": True},
    )
    policy = McpToolPolicy(
        {"fixture:read_note": McpToolRule(RiskLevel.READ_ONLY)}
    )
    decision = policy.evaluate("fixture", destructive)
    assert decision.risk is RiskLevel.HIGH_RISK
    assert decision.requires_approval
    assert "server marks tool as destructive" in decision.reasons
    assert "tool may interact with external systems" in decision.reasons
