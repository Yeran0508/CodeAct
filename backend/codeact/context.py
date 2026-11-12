from __future__ import annotations

from dataclasses import dataclass

TRUNCATION_MARKER = "\n... output truncated ...\n"


@dataclass(frozen=True)
class TruncationResult:
    text: str
    original_chars: int
    removed_chars: int

    @property
    def was_truncated(self) -> bool:
        return self.removed_chars > 0


def truncate_text(
    value: str,
    limit: int,
    *,
    marker: str = TRUNCATION_MARKER,
) -> TruncationResult:
    """Deterministically fit text within a character budget, preserving both ends."""
    if limit < 0:
        raise ValueError("character limit must not be negative")
    original_chars = len(value)
    if original_chars <= limit:
        return TruncationResult(value, original_chars, 0)
    if limit == 0:
        return TruncationResult("", original_chars, original_chars)
    if limit <= len(marker):
        return TruncationResult(marker[:limit], original_chars, original_chars)

    preserved_chars = limit - len(marker)
    head_size = (preserved_chars + 1) // 2
    tail_size = preserved_chars - head_size
    tail = value[-tail_size:] if tail_size else ""
    text = value[:head_size] + marker + tail
    return TruncationResult(text, original_chars, original_chars - preserved_chars)


def truncate_output(value: str, limit: int) -> tuple[str, int]:
    """Compatibility wrapper for executor output truncation."""
    result = truncate_text(value, limit)
    return result.text, result.removed_chars
