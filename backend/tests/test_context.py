import pytest
from codeact.context import TRUNCATION_MARKER, truncate_output, truncate_text


def test_short_output_is_unchanged() -> None:
    assert truncate_output("hello", 10) == ("hello", 0)


def test_long_output_keeps_head_tail_and_reports_removed_chars() -> None:
    value, removed = truncate_output("a" * 50 + "z" * 50, 50)
    assert value.startswith("a")
    assert value.endswith("z")
    assert "output truncated" in value
    assert removed > 0
    assert len(value) == 50


@pytest.mark.parametrize("limit", [0, 1, len(TRUNCATION_MARKER) - 1])
def test_tiny_budget_never_exceeds_limit(limit: int) -> None:
    result = truncate_text("x" * 100, limit)
    assert len(result.text) <= limit
    assert result.original_chars == 100
    assert result.removed_chars == 100
    assert result.was_truncated


def test_truncation_is_deterministic_and_keeps_unicode_character_boundaries() -> None:
    value = "开头-" + "中" * 40 + "-结尾"
    first = truncate_text(value, 35)
    second = truncate_text(value, 35)
    assert first == second
    assert first.text.startswith("开头-")
    assert first.text.endswith("-结尾")
    assert len(first.text) == 35
    assert first.original_chars - first.removed_chars == 35 - len(TRUNCATION_MARKER)


def test_invalid_negative_budget_is_rejected() -> None:
    with pytest.raises(ValueError, match="limit"):
        truncate_text("value", -1)
