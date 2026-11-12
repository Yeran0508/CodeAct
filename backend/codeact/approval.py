from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from codeact.models import Action


def action_digest(action: Action) -> str:
    payload = json.dumps(
        {
            "answer": action.answer,
            "code": action.code,
            "kind": action.kind.value,
            "language": action.language.value,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class ApprovalGrant:
    grant_id: str
    action_digest: str
    reasons: tuple[str, ...]
    approver: str
    issued_at: datetime
    expires_at: datetime

    @classmethod
    def issue(
        cls,
        action: Action,
        reasons: tuple[str, ...],
        *,
        approver: str,
        ttl: timedelta,
        now: datetime | None = None,
    ) -> ApprovalGrant:
        issued_at = now or datetime.now(UTC)
        if issued_at.tzinfo is None:
            raise ValueError("approval timestamps must be timezone-aware")
        if ttl <= timedelta(0):
            raise ValueError("approval ttl must be positive")
        if not approver.strip():
            raise ValueError("approver is required")
        return cls(
            grant_id=str(uuid.uuid4()),
            action_digest=action_digest(action),
            reasons=tuple(sorted(reasons)),
            approver=approver,
            issued_at=issued_at,
            expires_at=issued_at + ttl,
        )

    @classmethod
    def issue_for_digest(
        cls,
        digest: str,
        reasons: tuple[str, ...],
        *,
        approver: str,
        ttl: timedelta,
        now: datetime | None = None,
    ) -> ApprovalGrant:
        issued_at = now or datetime.now(UTC)
        if issued_at.tzinfo is None:
            raise ValueError("approval timestamps must be timezone-aware")
        if ttl <= timedelta(0):
            raise ValueError("approval ttl must be positive")
        if not approver.strip():
            raise ValueError("approver is required")
        if len(digest) != 64:
            raise ValueError("approval digest must be a SHA-256 hex digest")
        try:
            int(digest, 16)
        except ValueError as error:
            raise ValueError("approval digest must be a SHA-256 hex digest") from error
        return cls(
            grant_id=str(uuid.uuid4()),
            action_digest=digest.lower(),
            reasons=tuple(sorted(reasons)),
            approver=approver,
            issued_at=issued_at,
            expires_at=issued_at + ttl,
        )

    def is_valid(
        self,
        action: Action,
        reasons: tuple[str, ...],
        *,
        now: datetime,
    ) -> bool:
        if now.tzinfo is None:
            raise ValueError("validation timestamp must be timezone-aware")
        return (
            self.issued_at <= now < self.expires_at
            and self.action_digest == action_digest(action)
            and self.reasons == tuple(sorted(reasons))
        )

    def is_valid_for_digest(
        self,
        digest: str,
        reasons: tuple[str, ...],
        *,
        now: datetime,
    ) -> bool:
        if now.tzinfo is None:
            raise ValueError("validation timestamp must be timezone-aware")
        return (
            self.issued_at <= now < self.expires_at
            and self.action_digest == digest
            and self.reasons == tuple(sorted(reasons))
        )


class BoundApprovalGate:
    """Consume exact, unexpired grants once."""

    def __init__(
        self,
        grants: list[ApprovalGrant] | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._grants = {grant.grant_id: grant for grant in grants or []}
        self._clock = clock or (lambda: datetime.now(UTC))

    def add(self, grant: ApprovalGrant) -> None:
        if grant.grant_id in self._grants:
            raise ValueError("approval grant already exists")
        self._grants[grant.grant_id] = grant

    def authorize(self, action: Action, reasons: tuple[str, ...]) -> ApprovalGrant | None:
        return self.authorize_digest(action_digest(action), reasons)

    def authorize_digest(
        self, digest: str, reasons: tuple[str, ...]
    ) -> ApprovalGrant | None:
        now = self._clock()
        for grant_id, grant in tuple(self._grants.items()):
            if grant.is_valid_for_digest(digest, reasons, now=now):
                del self._grants[grant_id]
                return grant
        return None
