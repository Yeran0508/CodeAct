from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class McpServerConfig:
    server_id: str
    command: str
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    request_timeout_seconds: float = 30.0
    max_message_bytes: int = 4 * 1024 * 1024

    def __post_init__(self) -> None:
        if not self.server_id.strip():
            raise ValueError("server_id is required")
        if not self.command.strip():
            raise ValueError("command is required")
        if self.request_timeout_seconds <= 0:
            raise ValueError("request timeout must be positive")
        if self.max_message_bytes < 1024:
            raise ValueError("max message bytes must be at least 1024")


@dataclass(frozen=True)
class McpTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    annotations: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_wire(cls, value: dict[str, Any]) -> McpTool:
        name = value.get("name")
        schema = value.get("inputSchema")
        if not isinstance(name, str) or not name:
            raise ValueError("MCP tool name is required")
        if not isinstance(schema, dict):
            raise ValueError(f"MCP tool {name} has no valid inputSchema")
        description = value.get("description", "")
        annotations = value.get("annotations", {})
        if not isinstance(description, str) or not isinstance(annotations, dict):
            raise ValueError(f"MCP tool {name} metadata is invalid")
        return cls(name, description, schema, annotations)
