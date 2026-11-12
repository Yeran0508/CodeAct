import pytest

from scripts.benchmark_m3 import percentile, summarize


def test_percentile_interpolates_sorted_samples() -> None:
    samples = [50.0, 10.0, 40.0, 20.0, 30.0]
    assert percentile(samples, 0.5) == 30.0
    assert percentile(samples, 0.95) == pytest.approx(48.0)


def test_summary_preserves_raw_samples_and_bounds() -> None:
    result = summarize([3.3339, 1.1111, 2.2222])
    assert result == {
        "samples_ms": [3.334, 1.111, 2.222],
        "p50_ms": 2.222,
        "p95_ms": 3.223,
        "min_ms": 1.111,
        "max_ms": 3.334,
    }
