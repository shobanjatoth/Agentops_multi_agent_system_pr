import pytest
from fastapi.testclient import TestClient

from app.eval_tracker import EvalTracker, aggregate_metrics


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTOPS_DB_PATH", str(tmp_path / "metrics_test.db"))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    import importlib

    import app.eval_tracker as et
    importlib.reload(et)

    from app.main import app
    return TestClient(app)


def _tracker(tmp_path, monkeypatch, name="agg.db"):
    monkeypatch.setenv("AGENTOPS_DB_PATH", str(tmp_path / name))
    import importlib

    import app.eval_tracker as et
    importlib.reload(et)
    return et, et.EvalTracker(task_id="agg-task")


def test_aggregate_metrics_empty_db(tmp_path, monkeypatch):
    et, _ = _tracker(tmp_path, monkeypatch)
    metrics = et.aggregate_metrics()
    assert metrics["total_tasks"] == 0
    assert metrics["success_rate_pct"] is None
    assert metrics["per_node"] == {}


def test_aggregate_metrics_computes_success_rate(tmp_path, monkeypatch):
    et, tracker1 = _tracker(tmp_path, monkeypatch, "agg2.db")
    tracker1.start_task("task 1")
    tracker1.log_node(node="triage", input_summary="a", output_summary="b", latency_ms=5.0, cost_usd=0.001)
    tracker1.update_task_status("done")

    tracker2 = et.EvalTracker(task_id="agg-task-2")
    tracker2.start_task("task 2")
    tracker2.log_node(node="triage", input_summary="c", output_summary="d", latency_ms=3.0, passed=False)
    tracker2.update_task_status("failed")

    metrics = et.aggregate_metrics()
    assert metrics["total_tasks"] == 2
    assert metrics["success_rate_pct"] == 50.0
    assert metrics["per_node"]["triage"]["calls"] == 2
    assert metrics["per_node"]["triage"]["failures"] == 1


def test_metrics_endpoint_returns_200(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert "total_tasks" in body
    assert "per_node" in body


def test_batch_endpoint_rejects_empty_list(client):
    resp = client.post("/tasks/batch", json={"tasks": []})
    assert resp.status_code == 400


def test_batch_endpoint_processes_multiple_tasks_concurrently(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTOPS_DB_PATH", str(tmp_path / "batch_test.db"))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    import importlib

    import app.eval_tracker as et
    importlib.reload(et)

    import app.main as main_module
    from app.llm import LLMResult

    class FakeLLM:
        def complete(self, system, prompt, max_tokens=1024, temperature=0.2):
            if "exactly ONE next action" in system:
                return LLMResult(
                    text='{"type": "notify_slack", "target": "#eng", "body": "ack"}',
                    input_tokens=40, output_tokens=15, latency_ms=3.0,
                )
            return LLMResult(text="bug", input_tokens=8, output_tokens=1, latency_ms=1.0)

    monkeypatch.setattr(main_module, "LLMClient", lambda: FakeLLM())

    from fastapi.testclient import TestClient
    client = TestClient(main_module.app)

    resp = client.post(
        "/tasks/batch",
        json={
            "tasks": [
                {"description": "Login broken on Safari", "repo": "org/app"},
                {"description": "Add dark mode toggle", "repo": "org/app"},
                {"description": "Docs are unclear about setup", "repo": "org/app"},
            ]
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["batch_size"] == 3
    assert body["max_concurrent"] == main_module.MAX_CONCURRENT_TASKS
    assert len(body["results"]) == 3
    assert all(r["status"] in ("done", "awaiting_approval", "failed") for r in body["results"])
