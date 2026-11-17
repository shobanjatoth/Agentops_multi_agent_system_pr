import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.approval import approval_store


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTOPS_DB_PATH", str(tmp_path / "api_test.db"))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    return TestClient(app)


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["approval_store_backend"] in ("redis", "memory", "memory-fallback")


def test_get_unknown_task_returns_empty_summary(client):
    resp = client.get("/tasks/does-not-exist")
    assert resp.status_code == 200
    body = resp.json()
    assert body["steps"] == []


def test_approve_unknown_task_returns_404(client):
    resp = client.post("/tasks/does-not-exist/approve", json={"approved": True})
    assert resp.status_code == 404


def test_pending_approvals_empty_by_default(client):
    approval_store.clear()
    resp = client.get("/tasks/pending/approvals")
    assert resp.status_code == 200
    assert resp.json() == {}


def test_approve_resolves_pending_task(client):
    approval_store.add("api-task-1", {"type": "merge_pr", "body": "x"}, risk_score=0.9)
    resp = client.post("/tasks/api-task-1/approve", json={"approved": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["approved"] is True
    assert body["executed"] is False
    assert body["authorization_status"] == "approved"
    # second call should now 404 since it was already resolved
    resp2 = client.post("/tasks/api-task-1/approve", json={"approved": True})
    assert resp2.status_code == 404


def test_rejects_blank_description(client):
    resp = client.post("/tasks/batch", json={"tasks": [{"description": "   "}]})
    assert resp.status_code == 422


def test_rejects_invalid_repo_slug(client):
    resp = client.post("/tasks/batch", json={"tasks": [{"description": "login is broken", "repo": "../secret"}]})
    assert resp.status_code == 422
