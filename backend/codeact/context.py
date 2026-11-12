from __future__ import annotations


def truncate_output(value: str, limit: int) -> tuple[str, int]:
    if len(value) <= limit:
        return value, 0
    marker = "\n... output truncated ...\n"
    available = max(0, limit - len(marker))
    head_size = available // 2
    tail_size = available - head_size
    truncated = len(value) - available
    return value[:head_size] + marker + value[-tail_size:], truncated
