from typing import Any

import pytest
from codeact.mcp.client import HANDSHAKE_PROTOCOL_VERSION, McpClient, McpClientManager
from codeact.mcp.models import McpServerConfig
from codeact.mcp.transport import McpProtocolError


class FakeTransport:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = iter(responses)
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.notifications: list[tuple[str, dict[str, Any] | None]] = []
        self.closed = False

    def request(self, method, params):
        self.requests.append((method, dict(params)))
        return next(self.responses)

    def notify(self, method, params=None):
        self.notifications.append((method, dict(params) if params is not None else None))

    def close(self):
        self.closed = True


def initialize_result(version: str = HANDSHAKE_PROTOCOL_VERSION) -> dict[str, Any]:
    return {
        "protocolVersion": version,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": "fixture", "version": "1.0.0"},
    }


def test_connect_performs_handshake_then_initialized_notification() -> None:
    transport = FakeTransport([initialize_result()])
    client = McpClient(transport)
    result = client.connect()
    method, params = transport.requests[0]
    assert method == "initialize"
    assert params["protocolVersion"] == HANDSHAKE_PROTOCOL_VERSION
    assert params["clientInfo"]["name"] == "codeact-runtime"
    assert transport.notifications == [("notifications/initialized", None)]
    assert result["serverInfo"]["name"] == "fixture"


def test_connect_rejects_unsupported_version_or_missing_tools() -> None:
    with pytest.raises(McpProtocolError, match="unsupported"):
        McpClient(FakeTransport([initialize_result("2024-11-05")])).connect()
    result = initialize_result()
    result["capabilities"] = {}
    with pytest.raises(McpProtocolError, match="tools capability"):
        McpClient(FakeTransport([result])).connect()


def test_list_tools_follows_pagination_and_preserves_schema() -> None:
    transport = FakeTransport(
        [
            initialize_result(),
            {
                "tools": [
                    {
                        "name": "read_note",
                        "description": "Read a fixture note",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"name": {"type": "string"}},
                            "required": ["name"],
                        },
                    }
                ],
                "nextCursor": "page-2",
            },
            {
                "tools": [
                    {
                        "name": "sum_values",
                        "description": "Sum values",
                        "inputSchema": {"type": "object"},
                        "annotations": {"readOnlyHint": True},
                    }
                ]
            },
        ]
    )
    client = McpClient(transport)
    client.connect()
    tools = client.list_tools()
    assert [tool.name for tool in tools] == ["read_note", "sum_values"]
    assert tools[0].input_schema["required"] == ["name"]
    assert tools[1].annotations["readOnlyHint"] is True
    assert transport.requests[-1] == ("tools/list", {"cursor": "page-2"})


def test_list_tools_requires_connection_and_rejects_duplicates() -> None:
    with pytest.raises(RuntimeError, match="connect"):
        McpClient(FakeTransport([])).list_tools()
    transport = FakeTransport(
        [
            initialize_result(),
            {
                "tools": [
                    {"name": "same", "inputSchema": {"type": "object"}},
                    {"name": "same", "inputSchema": {"type": "object"}},
                ]
            },
        ]
    )
    client = McpClient(transport)
    client.connect()
    with pytest.raises(McpProtocolError, match="duplicate"):
        client.list_tools()


def test_manager_only_spawns_allowlisted_server() -> None:
    config = McpServerConfig("fixture", "python", ("server.py",))
    transports: list[FakeTransport] = []

    def factory(selected):
        assert selected == config
        transport = FakeTransport([initialize_result()])
        transports.append(transport)
        return transport

    manager = McpClientManager([config], transport_factory=factory)
    assert manager.allowed_server_ids == ("fixture",)
    with pytest.raises(PermissionError, match="not allowlisted"):
        manager.connect("unknown")
    manager.connect("fixture")
    assert len(transports) == 1


def test_server_config_validates_process_limits() -> None:
    with pytest.raises(ValueError, match="server_id"):
        McpServerConfig("", "python")
    with pytest.raises(ValueError, match="timeout"):
        McpServerConfig("fixture", "python", request_timeout_seconds=0)
    with pytest.raises(ValueError, match="message bytes"):
        McpServerConfig("fixture", "python", max_message_bytes=100)
