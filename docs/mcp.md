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

## References

- [MCP lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle)
- [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
- [MCP transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
