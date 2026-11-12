# MCP integration

## Supported lifecycle

CodeAct currently implements the MCP 2025-11-25 handshake lifecycle for local stdio servers:

1. send initialize with protocolVersion, capabilities, and clientInfo;
2. require the exact version, serverInfo, and tools capability;
3. send notifications/initialized;
4. follow cursor pagination across tools/list.

The protocol is intentionally pinned. The newer 2026-07-28 stateless lifecycle uses
server/discover and per-request metadata and is not yet claimed as supported.

## Transport boundary

StdioJsonRpcTransport launches only a command selected through McpClientManager's allowlist. It
uses newline-delimited JSON-RPC 2.0, enforces timeout and byte limits, rejects malformed envelopes,
handles server ping requests, and closes the child process.

The child receives only PATH and explicitly configured environment variables. Parent credentials
and unrelated values are not inherited implicitly. Server stdout is protocol-only; diagnostics
belong on stderr.

## Tool-call safety

The client calls only names returned by tools/list. Arguments are validated against each tool's
Draft 2020-12 inputSchema with jsonschema 4.26.0 before any request is sent.

Host-owned McpToolPolicy rules classify server_id:tool_name as read-only, write, or high-risk.
Missing rules default to high-risk. Server annotations may elevate a host rule when
destructiveHint or openWorldHint is true, but readOnlyHint cannot lower host policy.

Write and high-risk calls require a one-time ApprovalGrant. Its SHA-256 covers the exact server
ID, tool name, and canonical arguments. Changed arguments cannot reuse an earlier grant.

## References

- [MCP lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle)
- [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
- [MCP transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
