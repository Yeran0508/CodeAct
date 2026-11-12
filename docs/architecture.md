# Architecture

## M0 execution path

~~~text
task + history + observation
            |
       ModelClient
            |
       typed Action
            |
     ActionPolicy ---- high risk ----> ApprovalGate
            |                              |
            v                              v
     DockerExecutor                  terminal result
            |
       Observation ----> next model step
~~~

AgentRuntime owns deterministic control flow. A model adapter only proposes a typed action and
cannot execute code. ActionPolicy classifies it before DockerExecutor starts a disposable
container and converts the process result into an Observation.

For WRITE and HIGH_RISK actions, AgentRuntime asks WorkspaceManager for a snapshot before calling
the executor. A successful action keeps its changes and closes the snapshot. A failed or timed-out
action restores the previous tree before its observation reaches the next model step. Snapshots
live beside the workspace rather than inside the model-visible directory.

High-risk execution requires an ApprovalGrant. Its SHA-256 covers action kind, language, code, and
answer using canonical JSON. The grant also binds the sorted risk reasons, approver identity,
timezone-aware issue time, and expiration. BoundApprovalGate accepts an exact match once and then
removes it, so a grant cannot approve changed code or be replayed.

When configured, AuditLogger records run start, proposed actions, approval denials, execution
results, rollback status, and terminal results. Explicit configured secrets plus common bearer and
key-value credentials are redacted recursively before serialization. Each append-only JSONL event
contains the previous event hash and a hash of its own canonical contents. Verification detects
edits, deletion from the front or middle, reordering, malformed lines, and broken links. This is
tamper evidence, not a claim that a host administrator cannot delete the entire log.

The executor disables networking, limits CPU, memory and PIDs, drops Linux capabilities, sets
no-new-privileges, and runs as UID/GID 65534. The task workspace is the only writable bind mount.
This is a development boundary, not a hardened multi-tenant claim. Later M1 modules must address
approval integrity, audit logs, and adversarial tests before untrusted use.

## Trust boundaries

- Model output is untrusted until policy evaluation.
- Tool, file, command, and web output is data, never an instruction source.
- The action container never receives the privileged Docker socket.
- The runtime resolves host paths instead of accepting model-generated host paths.
- Approval defaults to deny; exact action-bound grants are checked before the executor.
- Audit files belong outside model-visible workspaces and must be protected by host permissions.

Before execution and snapshotting, the runtime rejects workspace symlinks that resolve outside the
workspace root. Static policy conservatively requires approval for dynamic or encoded shell
execution, process-exhaustion patterns, nested Python process/code execution, deletion, network
modules, remote pushes, permission changes, and Docker daemon operations. These checks reduce
accidental risk but do not replace container isolation.

## MCP client boundary

McpClientManager is the only component allowed to select a server process. Unknown server IDs are
rejected before process creation. The stdio transport inherits only PATH plus explicit environment
entries, applies newline message and timeout limits, and validates JSON-RPC 2.0 responses.

McpClient pins the valid 2025-11-25 handshake lifecycle: initialize, capability validation,
notifications/initialized, then cursor-aware tools/list. Supporting the newer stateless lifecycle
will require explicit server/discover negotiation rather than silently changing this contract.

## Warm sandbox pool

WarmSandboxPool owns a fixed target number of clean backend handles. A lease removes one handle
from the available queue. Release never returns that handle to the queue: the backend destroys it
and asynchronously creates a clean replacement. This preserves session isolation while allowing
another already-warm handle to serve the next acquisition.

Acquisition has a bounded deadline and discards unhealthy available handles. Pool close is
idempotent, rejects new work, waits briefly for replacement workers, and destroys both available
and leased live handles. PoolStats reports target, live, available, leased, and replacements in
flight without exposing backend-specific state. If asynchronous creation fails, its worker records
the failure and retries at the configured interval until capacity recovers or close signals it to
stop; acquisition deadlines remain bounded during an outage.

DockerWarmBackend implements that lifecycle using prestarted, sleeping containers. Each container
has a tmpfs `/workspace`, so multiple actions in one DockerSandboxSession see the same files while
no host directory is exposed. Closing the session destroys the entire container and the pool
creates a fresh replacement; a dirty filesystem is never placed back into the queue.

The backend disables networking, makes the image filesystem read-only, drops all capabilities,
sets no-new-privileges, and applies CPU, memory, PID, tmpfs-size, execution-time, and output bounds.
It runs as the configured UID/GID (the host user by default, or 65534 when the host is root).
These controls reduce blast radius but do not make Docker Desktop or a shared daemon a hardened
multi-tenant security boundary.

## Stop conditions

The loop ends on finish, exhausted steps, too many consecutive failures, or denied approval.
Runtime ownership prevents the model from silently disabling these limits.
