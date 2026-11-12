# M2 MCP acceptance - 2026-11-12

## Scope

This validates CodeAct's local MCP 2025-11-25 stdio integration. It covers lifecycle, discovery,
Schema validation, host policy, exact approval, untrusted results, and audit. It does not claim
support for remote Streamable HTTP or the 2026-07-28 stateless lifecycle.

## Environment

- Python 3.12.10 test image
- CodeAct 0.3.0
- jsonschema 4.26.0 with Draft 2020-12 validation
- Local standard-library fixture server over newline-delimited JSON-RPC 2.0

## Reproduction

~~~bash
docker compose build test
docker compose run --rm test
docker compose run --rm test ruff check .
docker run --rm -e PYTHONPATH=/src/backend -v "$PWD:/src:ro" +  codeact-test python /src/scripts/verify_m2.py
~~~

## Result

The fixture server completed initialize and notifications/initialized, exposed read_note and
write_note, and received real tools/call requests. The acceptance script verified:

- read_note ran without approval under an explicit host read-only rule;
- its injected instruction text remained inside an untrusted-data wrapper;
- write_note was denied without approval and did not create state;
- a one-time grant for the exact server/tool/arguments allowed one write;
- six requested/denied/finished audit events formed a valid hash chain;
- the configured secret appeared in the in-memory result/state but not in the audit file.

Output:

~~~text
M2 verification passed: tools=read_note,write_note denied_without_approval=true approved_write=true audit_events=6 secrets_redacted=true
~~~

The complete gate reported 62 passed, 2 Docker integration tests skipped by default, 93.98%
coverage, and a passing Ruff check.

## Limitations

- Only the 2025-11-25 handshake lifecycle and local stdio transport are supported.
- The fixture server is deterministic test infrastructure, not an external production server.
- Server annotations are untrusted hints and can only elevate host policy.
- Untrusted-data markers help model interpretation but do not guarantee prompt-injection immunity.
- Stdio stderr is not yet routed into structured runtime diagnostics.
