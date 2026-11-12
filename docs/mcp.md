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

## Untrusted results and audit

tools/call responses must contain an array of content objects. isError must be boolean and optional
structuredContent must be an object. Tool-level errors remain data rather than becoming protocol
exceptions; malformed response shapes are protocol errors.

McpToolResult.to_model_text places serialized content inside an explicit untrusted-data boundary
and applies the same observable head/tail truncation used for command output. This marker is a
model instruction aid, not a security boundary: every later proposed action still passes runtime
policy and approval.

When AuditLogger is configured, the client records requested, denied, and finished calls. Events
include call digest, risk reasons, approval ID, arguments, and result metadata. SecretRedactor
sanitizes arguments and content before the hash-chained event reaches disk.

## References

- [MCP lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle)
- [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
- [MCP transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)

## Reproducible fixture

scripts/mcp_fixture_server.py is a dependency-free stdio server that exposes read_note and
write_note. scripts/verify_m2.py launches it through the real allowlist and transport, discovers
both tools, checks denial before approval, issues an exact one-time grant, verifies the mutation,
and validates six redacted hash-chain events.
