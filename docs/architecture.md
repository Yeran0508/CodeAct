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

## Stop conditions

The loop ends on finish, exhausted steps, too many consecutive failures, or denied approval.
Runtime ownership prevents the model from silently disabling these limits.
