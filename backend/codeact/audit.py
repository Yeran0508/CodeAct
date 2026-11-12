from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_KEY_VALUE_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|token|password|secret)\b(\s*[:=]\s*)([^\s,;]+)"
)
_BEARER_SECRET = re.compile(r"(?i)\b(bearer\s+)([a-z0-9._~+/-]+=*)")
_REDACTED = "[REDACTED]"


class AuditIntegrityError(ValueError):
    pass


class SecretRedactor:
    def __init__(self, secrets: Sequence[str] = ()) -> None:
        self._secrets = tuple(
            sorted((secret for secret in secrets if secret), key=len, reverse=True)
        )

    def redact_text(self, value: str) -> str:
        result = value
        for secret in self._secrets:
            result = result.replace(secret, _REDACTED)
        result = _BEARER_SECRET.sub(lambda match: match.group(1) + _REDACTED, result)
        return _KEY_VALUE_SECRET.sub(
            lambda match: match.group(1) + match.group(2) + _REDACTED,
            result,
        )

    def redact(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, Mapping):
            return {str(key): self.redact(item) for key, item in value.items()}
        if isinstance(value, tuple | list):
            return [self.redact(item) for item in value]
        return value


class AuditLogger:
    def __init__(
        self,
        path: Path,
        *,
        redactor: SecretRedactor | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = path
        self.redactor = redactor or SecretRedactor()
        self.clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()

    @staticmethod
    def _hash(contents: dict[str, Any]) -> str:
        canonical = json.dumps(
            contents, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        return hashlib.sha256(canonical).hexdigest()

    def _previous_hash(self) -> str | None:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return None
        with self.path.open(encoding="utf-8") as stream:
            last_line = None
            for line in stream:
                if line.strip():
                    last_line = line
        if last_line is None:
            return None
        return json.loads(last_line)["event_hash"]

    def record(self, event_type: str, run_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError("audit timestamps must be timezone-aware")
        if not event_type or not run_id:
            raise ValueError("event_type and run_id are required")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            event = {
                "event_type": event_type,
                "payload": self.redactor.redact(payload),
                "previous_hash": self._previous_hash(),
                "run_id": run_id,
                "timestamp": now.isoformat(),
            }
            event["event_hash"] = self._hash(event)
            encoded = (json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n").encode()
            descriptor = os.open(
                self.path,
                os.O_APPEND | os.O_CREAT | os.O_WRONLY,
                0o600,
            )
            try:
                os.write(descriptor, encoded)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return event

    def verify(self) -> int:
        previous_hash = None
        count = 0
        if not self.path.exists():
            return 0
        with self.path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                try:
                    event = json.loads(line)
                    event_hash = event.pop("event_hash")
                except (json.JSONDecodeError, KeyError) as error:
                    raise AuditIntegrityError(
                        f"invalid audit event at line {line_number}"
                    ) from error
                if event.get("previous_hash") != previous_hash:
                    raise AuditIntegrityError(f"broken audit chain at line {line_number}")
                if self._hash(event) != event_hash:
                    raise AuditIntegrityError(f"invalid audit hash at line {line_number}")
                previous_hash = event_hash
                count += 1
        return count
