import io
import json
from unittest.mock import patch

import pytest
from codeact.mcp.models import McpServerConfig
from codeact.mcp.transport import McpProtocolError, McpTransportError, StdioJsonRpcTransport


class FakeProcess:
    def __init__(self, messages: list[dict] | None = None, raw: bytes | None = None) -> None:
        data = raw
        if data is None:
            data = b"".join(
                json.dumps(message, separators=(",", ":")).encode() + b"\n"
                for message in messages or []
            )
        self.stdout = io.BytesIO(data)
        self.stdin = io.BytesIO()
        self.returncode = None
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.returncode = -9


def config(**overrides) -> McpServerConfig:
    values = {
        "server_id": "fixture",
        "command": "python",
        "args": ("server.py",),
        "request_timeout_seconds": 0.1,
    }
    values.update(overrides)
    return McpServerConfig(**values)


def test_stdio_request_writes_jsonrpc_and_handles_ping() -> None:
    process = FakeProcess(
        [
            {"jsonrpc": "2.0", "id": 99, "method": "ping"},
            {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}},
        ]
    )
    with patch("codeact.mcp.transport.subprocess.Popen", return_value=process) as popen:
        transport = StdioJsonRpcTransport(config(env={"FIXTURE": "yes"}))
        assert transport.request("tools/list", {}) == {"tools": []}
    written = process.stdin.getvalue().decode().splitlines()
    assert json.loads(written[0]) == {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {},
    }
    assert json.loads(written[1]) == {"jsonrpc": "2.0", "id": 99, "result": {}}
    assert popen.call_args.kwargs["env"]["FIXTURE"] == "yes"
    assert "HOME" not in popen.call_args.kwargs["env"]


def test_stdio_notification_and_close() -> None:
    process = FakeProcess()
    with patch("codeact.mcp.transport.subprocess.Popen", return_value=process):
        transport = StdioJsonRpcTransport(config())
        transport.notify("notifications/initialized")
        message = json.loads(process.stdin.getvalue())
        assert message == {"jsonrpc": "2.0", "method": "notifications/initialized"}
        transport.close()
    assert process.terminated


def test_stdio_rejects_error_invalid_envelope_and_large_request() -> None:
    error_process = FakeProcess(
        [{"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "missing"}}]
    )
    with patch("codeact.mcp.transport.subprocess.Popen", return_value=error_process):
        with pytest.raises(McpProtocolError, match="error response"):
            StdioJsonRpcTransport(config()).request("missing", {})

    invalid_process = FakeProcess([{"jsonrpc": "1.0", "id": 1, "result": {}}])
    with patch("codeact.mcp.transport.subprocess.Popen", return_value=invalid_process):
        with pytest.raises(McpProtocolError, match="envelope"):
            StdioJsonRpcTransport(config()).request("tools/list", {})

    process = FakeProcess()
    with patch("codeact.mcp.transport.subprocess.Popen", return_value=process):
        transport = StdioJsonRpcTransport(config(max_message_bytes=1024))
        with pytest.raises(McpTransportError, match="request exceeds"):
            transport.request("large", {"value": "x" * 2000})


def test_stdio_rejects_invalid_json_and_times_out() -> None:
    invalid_process = FakeProcess(raw=b"not-json\n")
    with patch("codeact.mcp.transport.subprocess.Popen", return_value=invalid_process):
        with pytest.raises(McpTransportError, match="reader failed"):
            StdioJsonRpcTransport(config()).request("tools/list", {})

    empty_process = FakeProcess()
    with patch("codeact.mcp.transport.subprocess.Popen", return_value=empty_process):
        with pytest.raises(McpTransportError, match="timed out"):
            StdioJsonRpcTransport(config()).request("tools/list", {})
