from __future__ import annotations

from collections.abc import Callable
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from codeact.approval import ApprovalGrant, BoundApprovalGate
from codeact.mcp.models import McpServerConfig, McpTool, tool_call_digest
from codeact.mcp.policy import McpToolPolicy
from codeact.mcp.transport import (
    JsonRpcTransport,
    McpProtocolError,
    StdioJsonRpcTransport,
)

HANDSHAKE_PROTOCOL_VERSION = "2025-11-25"


class McpToolValidationError(ValueError):
    pass


class McpClient:
    def __init__(
        self,
        transport: JsonRpcTransport,
        *,
        client_name: str = "codeact-runtime",
        client_version: str = "0.2.0",
        server_id: str = "unknown",
    ) -> None:
        self.transport = transport
        self.client_name = client_name
        self.client_version = client_version
        self.server_id = server_id
        self.server_info: dict[str, Any] | None = None
        self.tools: dict[str, McpTool] = {}

    def connect(self) -> dict[str, Any]:
        result = self.transport.request(
            "initialize",
            {
                "protocolVersion": HANDSHAKE_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": self.client_name, "version": self.client_version},
            },
        )
        if result.get("protocolVersion") != HANDSHAKE_PROTOCOL_VERSION:
            raise McpProtocolError("server selected an unsupported MCP protocol version")
        if not isinstance(result.get("serverInfo"), dict):
            raise McpProtocolError("initialize response has no serverInfo")
        capabilities = result.get("capabilities")
        if not isinstance(capabilities, dict) or not isinstance(capabilities.get("tools"), dict):
            raise McpProtocolError("MCP server does not advertise tools capability")
        self.server_info = result
        self.transport.notify("notifications/initialized")
        return result

    def list_tools(self) -> tuple[McpTool, ...]:
        if self.server_info is None:
            raise RuntimeError("MCP client must connect before listing tools")
        tools: dict[str, McpTool] = {}
        cursor: str | None = None
        while True:
            params = {"cursor": cursor} if cursor else {}
            result = self.transport.request("tools/list", params)
            wire_tools = result.get("tools")
            if not isinstance(wire_tools, list):
                raise McpProtocolError("tools/list result has no tools array")
            for value in wire_tools:
                if not isinstance(value, dict):
                    raise McpProtocolError("tools/list contains an invalid tool")
                tool = McpTool.from_wire(value)
                if tool.name in tools:
                    raise McpProtocolError(f"duplicate MCP tool name: {tool.name}")
                tools[tool.name] = tool
            next_cursor = result.get("nextCursor")
            if next_cursor is None:
                break
            if not isinstance(next_cursor, str) or not next_cursor:
                raise McpProtocolError("tools/list returned an invalid nextCursor")
            cursor = next_cursor
        self.tools = tools
        return tuple(tools.values())

    def close(self) -> None:
        self.transport.close()

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        policy: McpToolPolicy,
        approval_gate: BoundApprovalGate | None = None,
    ) -> tuple[dict[str, Any], ApprovalGrant | None]:
        tool = self.tools.get(name)
        if tool is None:
            raise KeyError(f"MCP tool was not discovered: {name}")
        try:
            Draft202012Validator.check_schema(tool.input_schema)
            Draft202012Validator(tool.input_schema).validate(arguments)
        except (SchemaError, ValidationError) as error:
            path = ".".join(str(part) for part in getattr(error, "absolute_path", ()))
            location = f" at {path}" if path else ""
            raise McpToolValidationError(
                f"invalid arguments for {name}{location}: {error.message}"
            ) from error

        decision = policy.evaluate(self.server_id, tool)
        approval = None
        if decision.requires_approval:
            digest = tool_call_digest(self.server_id, name, arguments)
            approval = (
                approval_gate.authorize_digest(digest, decision.reasons)
                if approval_gate is not None
                else None
            )
            if approval is None:
                raise PermissionError(f"MCP tool approval required: {decision.reasons}")
        result = self.transport.request("tools/call", {"name": name, "arguments": arguments})
        return result, approval


class McpClientManager:
    def __init__(
        self,
        configs: list[McpServerConfig],
        *,
        transport_factory: Callable[[McpServerConfig], JsonRpcTransport] = StdioJsonRpcTransport,
    ) -> None:
        self._configs = {config.server_id: config for config in configs}
        if len(self._configs) != len(configs):
            raise ValueError("duplicate MCP server_id")
        self._transport_factory = transport_factory

    @property
    def allowed_server_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._configs))

    def connect(self, server_id: str) -> McpClient:
        config = self._configs.get(server_id)
        if config is None:
            raise PermissionError(f"MCP server is not allowlisted: {server_id}")
        client = McpClient(self._transport_factory(config), server_id=server_id)
        client.connect()
        return client
