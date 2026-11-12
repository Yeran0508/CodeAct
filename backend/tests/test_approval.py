from datetime import UTC, datetime, timedelta

import pytest
from codeact.approval import ApprovalGrant, BoundApprovalGate, action_digest
from codeact.models import Action, CodeLanguage

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
REASONS = ("file deletion",)


def test_digest_is_stable_and_sensitive_to_code() -> None:
    first = Action.execute("rm file-a", CodeLanguage.BASH)
    same = Action.execute("rm file-a", CodeLanguage.BASH)
    changed = Action.execute("rm file-b", CodeLanguage.BASH)
    assert action_digest(first) == action_digest(same)
    assert action_digest(first) != action_digest(changed)


def test_grant_requires_identity_positive_ttl_and_aware_time() -> None:
    action = Action.execute("rm file", CodeLanguage.BASH)
    with pytest.raises(ValueError, match="approver"):
        ApprovalGrant.issue(action, REASONS, approver=" ", ttl=timedelta(minutes=1), now=NOW)
    with pytest.raises(ValueError, match="positive"):
        ApprovalGrant.issue(action, REASONS, approver="user", ttl=timedelta(0), now=NOW)
    with pytest.raises(ValueError, match="timezone-aware"):
        ApprovalGrant.issue(
            action,
            REASONS,
            approver="user",
            ttl=timedelta(minutes=1),
            now=NOW.replace(tzinfo=None),
        )


def test_gate_authorizes_exact_action_once() -> None:
    action = Action.execute("rm file", CodeLanguage.BASH)
    grant = ApprovalGrant.issue(
        action, REASONS, approver="user@example.test", ttl=timedelta(minutes=5), now=NOW
    )
    gate = BoundApprovalGate([grant], clock=lambda: NOW + timedelta(minutes=1))
    assert gate.authorize(action, REASONS) == grant
    assert gate.authorize(action, REASONS) is None


def test_gate_rejects_changed_action_reason_and_expired_grant() -> None:
    action = Action.execute("rm file", CodeLanguage.BASH)
    grant = ApprovalGrant.issue(
        action, REASONS, approver="user@example.test", ttl=timedelta(minutes=5), now=NOW
    )
    assert (
        BoundApprovalGate([grant], clock=lambda: NOW).authorize(
            Action.execute("rm other", CodeLanguage.BASH), REASONS
        )
        is None
    )
    assert (
        BoundApprovalGate([grant], clock=lambda: NOW).authorize(action, ("network access",))
        is None
    )
    assert (
        BoundApprovalGate([grant], clock=lambda: NOW + timedelta(minutes=5)).authorize(
            action, REASONS
        )
        is None
    )


def test_gate_rejects_naive_validation_clock_and_duplicate_id() -> None:
    action = Action.execute("rm file", CodeLanguage.BASH)
    grant = ApprovalGrant.issue(
        action, REASONS, approver="user@example.test", ttl=timedelta(minutes=5), now=NOW
    )
    gate = BoundApprovalGate([grant], clock=lambda: NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="timezone-aware"):
        gate.authorize(action, REASONS)
    with pytest.raises(ValueError, match="already exists"):
        BoundApprovalGate([grant]).add(grant)


def test_grant_can_bind_a_non_action_sha256_digest() -> None:
    digest = "a" * 64
    grant = ApprovalGrant.issue_for_digest(
        digest,
        ("MCP tool mutates state",),
        approver="user@example.test",
        ttl=timedelta(minutes=5),
        now=NOW,
    )
    gate = BoundApprovalGate([grant], clock=lambda: NOW)
    assert gate.authorize_digest(digest, ("MCP tool mutates state",)) == grant
    assert gate.authorize_digest(digest, ("MCP tool mutates state",)) is None


def test_non_action_grant_rejects_invalid_digest() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        ApprovalGrant.issue_for_digest(
            "not-a-digest",
            (),
            approver="user",
            ttl=timedelta(minutes=1),
            now=NOW,
        )
