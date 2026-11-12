from __future__ import annotations

import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from codeact.approval import ApprovalGrant, BoundApprovalGate
from codeact.audit import AuditLogger, SecretRedactor
from codeact.mcp.client import McpClientManager
from codeact.mcp.models import McpServerConfig, tool_call_digest
from codeact.mcp.policy import McpToolPolicy, McpToolRule
from codeact.models import RiskLevel

PROJECT_ROOT = Path(__file__).parents[1]
SERVER = PROJECT_ROOT / "scripts" / "mcp_fixture_server.py"


def main() -> None:
    now = datetime.now(UTC)
    with tempfile.TemporaryDirectory(prefix="codeact-m2-") as directory:
        root = Path(directory)
        state_path = root / "state.txt"
        audit = AuditLogger(
            root / "audit.jsonl",
            redactor=SecretRedactor(["private-note"]),
            clock=lambda: now,
        )
        config = McpServerConfig(
            "fixture",
            sys.executable,
            (str(SERVER),),
            env={"FIXTURE_STATE_PATH": str(state_path)},
            request_timeout_seconds=2,
        )
        client = McpClientManager(
            [config], audit_logger=audit, run_id="m2-acceptance"
        ).connect("fixture")
        policy = McpToolPolicy(
            {
                "fixture:read_note": McpToolRule(RiskLevel.READ_ONLY),
                "fixture:write_note": McpToolRule(
                    RiskLevel.WRITE, ("fixture state mutation",)
                ),
            }
        )
        try:
            tools = client.list_tools()
            read = client.call_tool("read_note", {"name": "intro"}, policy=policy)
            untrusted_text, _ = read.result.to_model_text()
            if "BEGIN UNTRUSTED MCP TOOL DATA" not in untrusted_text:
                raise RuntimeError("fixture result was not marked untrusted")
            try:
                client.call_tool(
                    "write_note", {"text": "private-note"}, policy=policy
                )
            except PermissionError:
                pass
            else:
                raise RuntimeError("write tool ran without approval")
            if state_path.exists():
                raise RuntimeError("denied tool call changed fixture state")

            arguments = {"text": "private-note"}
            reasons = (
                "fixture state mutation",
                "server marks tool as destructive",
            )
            grant = ApprovalGrant.issue_for_digest(
                tool_call_digest("fixture", "write_note", arguments),
                reasons,
                approver="m2-reviewer",
                ttl=timedelta(minutes=5),
                now=now,
            )
            outcome = client.call_tool(
                "write_note",
                arguments,
                policy=policy,
                approval_gate=BoundApprovalGate([grant], clock=lambda: now),
            )
            if outcome.approval_id != grant.grant_id:
                raise RuntimeError("approved call did not retain approval identity")
            if state_path.read_text() != "private-note":
                raise RuntimeError("approved fixture write did not complete")
        finally:
            client.close()

        event_count = audit.verify()
        if event_count != 6 or "private-note" in audit.path.read_text():
            raise RuntimeError("MCP audit verification failed")
        print(
            "M2 verification passed:",
            "tools=" + ",".join(tool.name for tool in tools),
            "denied_without_approval=true",
            "approved_write=true",
            "audit_events=6",
            "secrets_redacted=true",
        )


if __name__ == "__main__":
    main()
