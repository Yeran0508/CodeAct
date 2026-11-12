import pytest

from scripts.benchmark_m4 import FixtureProvider, benchmark


def test_fixture_provider_reports_real_cache_reuse_for_its_tokenizer() -> None:
    provider = FixtureProvider()
    first = provider.report_usage("hash", "stable prefix", "dynamic one")
    second = provider.report_usage("hash", "stable prefix", "dynamic two")
    assert first.cache_write_tokens == 2
    assert first.cache_read_tokens == 0
    assert second.cache_write_tokens == 0
    assert second.cache_read_tokens == 2


def test_benchmark_summary_retains_facts_with_fewer_fixture_tokens() -> None:
    result = benchmark(cases=3, budget=2400)
    without = result["without_summary"]
    with_summary = result["with_summary"]
    assert without["successes"] < 3
    assert with_summary["successes"] == 3
    assert with_summary["usage"]["input_tokens"] < without["usage"]["input_tokens"]
    assert with_summary["prefix_sha256"] == without["prefix_sha256"]


def test_benchmark_validates_configuration() -> None:
    with pytest.raises(ValueError, match="cases"):
        benchmark(0, 100)
    with pytest.raises(ValueError, match="budget"):
        benchmark(1, 0)
