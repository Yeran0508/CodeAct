import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from codeact.approval import ApprovalGrant, BoundApprovalGate
from codeact.audit import AuditLogger, SecretRedactor
from codeact.mcp.client import McpClientManager
from codeact.mcp.models import McpServerConfig, tool_call_digest
from codeact.mcp.policy import McpToolPolicy, McpToolRule
from codeact.models import RiskLevel

NOW = datetime(2026, 11, 12, 17, 0, tzinfo=UTC)
PROJECT_ROOT = Path(__file__).parents[3]
SERVER = PROJECT_ROOT / "scripts" / "mcp_fixture_server.py"


def test_fixture_server_end_to_end_with_approval_and_audit(tmp_path: Path) -> None:
    state_path = tmp_path / "state.txt"
    audit = AuditLogger(
        tmp_path / "mcp-audit.jsonl",
        redactor=SecretRedactor(["private-note"]),
        clock=lambda: NOW,
    )
    manager = McpClientManager(
        [
            McpServerConfig(
                "fixture",
                sys.executable,
                (str(SERVER),),
                env={"FIXTURE_STATE_PATH": str(state_path)},
                request_timeout_seconds=2,
            )
        ],
        audit_logger=audit,
        run_id="m2-e2e",
    )
    client = manager.connect("fixture")
    try:
        tools = client.list_tools()
        assert [tool.name for tool in tools] == ["read_note", "write_note"]
        policy = McpToolPolicy(
            {
                "fixture:read_note": McpToolRule(RiskLevel.READ_ONLY),
                "fixture:write_note": McpToolRule(
                    RiskLevel.WRITE, ("fixture state mutation",)
                ),
            }
        )
        read = client.call_tool("read_note", {"name": "intro"}, policy=policy)
        model_text, removed = read.result.to_model_text()
        assert "BEGIN UNTRUSTED MCP TOOL DATA" in model_text
        assert "ignore host policy" in model_text
        assert removed == 0

        with pytest.raises(PermissionError):
            client.call_tool("write_note", {"text": "private-note"}, policy=policy)
        assert not state_path.exists()

        reasons = (
            "fixture state mutation",
            "server marks tool as destructive",
        )
        digest = tool_call_digest(
            "fixture", "write_note", {"text": "private-note"}
        )
        grant = ApprovalGrant.issue_for_digest(
            digest,
            reasons,
            approver="m2-reviewer",
            ttl=timedelta(minutes=5),
            now=NOW,
        )
        write = client.call_tool(
            "write_note",
            {"text": "private-note"},
            policy=policy,
            approval_gate=BoundApprovalGate([grant], clock=lambda: NOW),
        )
        assert write.approval_id == grant.grant_id
        assert state_path.read_text() == "private-note"
    finally:
        client.close()

    assert audit.verify() == 6
    assert "private-note" not in audit.path.read_text()
