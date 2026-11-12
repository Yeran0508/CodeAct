import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from codeact.audit import AuditIntegrityError, AuditLogger, SecretRedactor

NOW = datetime(2026, 11, 12, 13, 0, tzinfo=UTC)


def test_redactor_handles_explicit_bearer_and_key_value_secrets() -> None:
    redactor = SecretRedactor(["exact-secret"])
    value = redactor.redact(
        {
            "message": "exact-secret Authorization: Bearer abc.def token=token-value",
            "nested": ["password: hunter2"],
        }
    )
    encoded = json.dumps(value)
    assert "exact-secret" not in encoded
    assert "abc.def" not in encoded
    assert "token-value" not in encoded
    assert "hunter2" not in encoded
    assert encoded.count("[REDACTED]") == 4


def test_logger_appends_hash_chained_events_and_verifies(tmp_path: Path) -> None:
    logger = AuditLogger(tmp_path / "audit.jsonl", clock=lambda: NOW)
    first = logger.record("run_started", "run-1", {"task": "test"})
    second = logger.record("run_finished", "run-1", {"status": "completed"})
    assert first["previous_hash"] is None
    assert second["previous_hash"] == first["event_hash"]
    assert logger.verify() == 2


def test_logger_detects_modified_deleted_and_invalid_events(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path, clock=lambda: NOW)
    logger.record("first", "run-1", {"value": 1})
    logger.record("second", "run-1", {"value": 2})
    lines = path.read_text().splitlines()

    modified = json.loads(lines[0])
    modified["payload"]["value"] = 99
    path.write_text(json.dumps(modified) + "\n" + lines[1] + "\n")
    with pytest.raises(AuditIntegrityError, match="hash"):
        logger.verify()

    path.write_text(lines[1] + "\n")
    with pytest.raises(AuditIntegrityError, match="chain"):
        logger.verify()

    path.write_text("{invalid}\n")
    with pytest.raises(AuditIntegrityError, match="invalid audit event"):
        logger.verify()


def test_logger_validates_metadata_and_time(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    with pytest.raises(ValueError, match="timezone-aware"):
        AuditLogger(path, clock=lambda: NOW.replace(tzinfo=None)).record("event", "run", {})
    logger = AuditLogger(path, clock=lambda: NOW)
    with pytest.raises(ValueError, match="required"):
        logger.record("", "run", {})
    assert logger.verify() == 0
