# Runtime Contract

M0 is a Python library, not an HTTP service.

## Action

- kind: execute or finish
- language: python or bash
- code: source text
- answer: final response for finish

## Observation

- stdout and stderr: bounded streams
- exit_code: integer or null after timeout
- duration_ms: wall-clock duration
- timed_out: deadline status
- truncated_chars: omitted stream character count

## Run result

- answer: final answer when completed
- stop_reason: completed, max_steps, failure_limit, or approval_denied
- steps: ordered action, policy, and observation records
- rolled_back: whether a failed mutating step restored its pre-execution snapshot
- approval_id: the consumed action-bound approval grant, or null

## Approval grant

- grant_id: unique identifier
- action_digest: SHA-256 of the canonical action payload
- reasons: exact normalized policy reasons
- approver: non-empty approving identity
- issued_at and expires_at: timezone-aware validity interval

Grants are exact, expiring, and one-time. Changing code, language, action kind, answer, or policy
reasons invalidates the grant.

The model adapter and approval UI are interfaces. Provider credentials and UI concerns do not
belong in the core runtime.
