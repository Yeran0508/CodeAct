from codeact.metrics import percentile, summarize_manifest


def test_metrics_aggregate_success_latency_usage_and_failures() -> None:
    manifest = {
        "tasks": {
            "a": {
                "status": "completed",
                "result": {
                    "success": True,
                    "duration_ms": 10,
                    "retries": 1,
                    "timeouts": 0,
                    "failure_category": None,
                    "usage": {"input_tokens": 20, "output_tokens": 5},
                },
            },
            "b": {
                "status": "completed",
                "result": {
                    "success": False,
                    "duration_ms": 30,
                    "retries": 0,
                    "timeouts": 1,
                    "failure_category": "timeout",
                    "usage": {
                        "input_tokens": 25,
                        "output_tokens": 6,
                        "cache_read_tokens": 10,
                        "cache_write_tokens": 2,
                    },
                },
            },
            "c": {"status": "failed", "result": None},
        }
    }
    metrics = summarize_manifest(manifest)
    assert metrics.tasks == 3
    assert metrics.successes == 1
    assert metrics.success_rate == 1 / 3
    assert metrics.duration_total_ms == 40
    assert metrics.duration_p50_ms == 20
    assert metrics.duration_p95_ms == 29
    assert metrics.input_tokens == 45
    assert metrics.output_tokens == 11
    assert metrics.cache_read_tokens == 10
    assert metrics.cache_write_tokens == 2
    assert metrics.retries == 1
    assert metrics.timeouts == 1
    assert metrics.failure_categories == {"runner_error": 1, "timeout": 1}


def test_metrics_handle_empty_manifest_and_percentile() -> None:
    metrics = summarize_manifest({"tasks": {}})
    assert metrics.tasks == 0
    assert metrics.success_rate == 0
    assert percentile([], 0.95) == 0
