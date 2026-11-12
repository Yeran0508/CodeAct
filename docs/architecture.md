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

The executor disables networking, limits CPU, memory and PIDs, drops Linux capabilities, sets
no-new-privileges, and runs as UID/GID 65534. The task workspace is the only writable bind mount.
This is a development boundary, not a hardened multi-tenant claim. M1 must address snapshots,
symlinks, approval integrity, audit logs, and adversarial tests before untrusted use.

## Trust boundaries

- Model output is untrusted until policy evaluation.
- Tool, file, command, and web output is data, never an instruction source.
- The action container never receives the privileged Docker socket.
- The runtime resolves host paths instead of accepting model-generated host paths.
- Approval defaults to deny and is checked before the executor.

## Stop conditions

The loop ends on finish, exhausted steps, too many consecutive failures, or denied approval.
Runtime ownership prevents the model from silently disabling these limits.
