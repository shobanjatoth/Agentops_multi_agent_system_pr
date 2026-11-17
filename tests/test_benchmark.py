"""
Runs the actual benchmark.py logic as part of the test suite. This is
what caught two incorrect scenario expectations during development (risk
scores that were miscalculated by hand when the scenarios were written) —
now that mistake class can't silently reappear, since run_benchmark()
raises if any scenario's expect_requires_approval doesn't match reality.
"""
import benchmark


def test_benchmark_runs_without_raising_and_meets_all_expectations():
    summary = benchmark.run_benchmark()
    assert summary["expectations_checked"] > 0
    assert summary["expectations_met"] == summary["expectations_checked"]


def test_benchmark_success_rate_is_reasonable():
    summary = benchmark.run_benchmark()
    # Not 100% (one scenario is designed to fail) and not too low either --
    # a sudden drop here means something in the graph/critic/approval logic broke.
    assert 80.0 <= summary["task_success_rate_pct"] < 100.0


def test_benchmark_has_at_least_one_designed_failure():
    summary = benchmark.run_benchmark()
    assert summary["failed_scenarios"] >= 1
