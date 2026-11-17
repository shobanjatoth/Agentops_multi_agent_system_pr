import os

from app.eval_tracker import EvalTracker


def test_log_node_and_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTOPS_DB_PATH", str(tmp_path / "test.db"))
    import importlib

    import app.eval_tracker as et
    importlib.reload(et)

    tracker = et.EvalTracker(task_id="task-1")
    tracker.start_task("Test task")
    tracker.log_node(
        node="triage",
        input_summary="in",
        output_summary="out",
        latency_ms=12.5,
        input_tokens=10,
        output_tokens=5,
        cost_usd=0.0001,
        passed=True,
    )
    tracker.log_node(
        node="critic",
        input_summary="in2",
        output_summary="out2",
        latency_ms=0.5,
        passed=False,
    )

    summary = tracker.task_summary()
    assert summary["task_id"] == "task-1"
    assert len(summary["steps"]) == 2
    assert summary["all_passed"] is False
    assert summary["total_latency_ms"] == 13.0


def test_dashboard_query_returns_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTOPS_DB_PATH", str(tmp_path / "test2.db"))
    import importlib

    import app.eval_tracker as et
    importlib.reload(et)

    tracker = et.EvalTracker(task_id="task-2")
    tracker.start_task("Another task")
    tracker.log_node(node="research", input_summary="x", output_summary="y", latency_ms=1.0)

    rows = et.dashboard_query()
    assert len(rows) >= 1
    assert rows[0]["task_id"] == "task-2"
