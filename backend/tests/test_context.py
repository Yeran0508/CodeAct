from codeact.context import truncate_output


def test_short_output_is_unchanged() -> None:
    assert truncate_output("hello", 10) == ("hello", 0)


def test_long_output_keeps_head_tail_and_reports_removed_chars() -> None:
    value, removed = truncate_output("a" * 50 + "z" * 50, 50)
    assert value.startswith("a")
    assert value.endswith("z")
    assert "output truncated" in value
    assert removed > 0
    assert len(value) == 50
