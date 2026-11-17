from app.agents.critic import critic_node, should_retry
from app.eval_tracker import EvalTracker


def _tracker(tmp_path, monkeypatch, name="t.db"):
    monkeypatch.setenv("AGENTOPS_DB_PATH", str(tmp_path / name))
    import importlib

    import app.eval_tracker as et
    importlib.reload(et)
    return et.EvalTracker(task_id="test-task")


def test_critic_passes_valid_action(tmp_path, monkeypatch):
    tracker = _tracker(tmp_path, monkeypatch)
    state = {
        "proposed_action": {"type": "post_comment", "body": "Investigating the issue now."},
        "revision_count": 0,
        "trace": [],
    }
    result = critic_node(state, tracker)
    assert result["critic_passed"] is True
    assert result["revision_count"] == 0


def test_critic_rejects_empty_body(tmp_path, monkeypatch):
    tracker = _tracker(tmp_path, monkeypatch, "t2.db")
    state = {
        "proposed_action": {"type": "post_comment", "body": ""},
        "revision_count": 0,
        "trace": [],
    }
    result = critic_node(state, tracker)
    assert result["critic_passed"] is False
    assert result["revision_count"] == 1


def test_critic_rejects_unknown_action_type(tmp_path, monkeypatch):
    tracker = _tracker(tmp_path, monkeypatch, "t3.db")
    state = {
        "proposed_action": {"type": "wipe_database", "body": "oops"},
        "revision_count": 0,
        "trace": [],
    }
    result = critic_node(state, tracker)
    assert result["critic_passed"] is False


def test_should_retry_stops_after_max_revisions():
    assert should_retry({"critic_passed": False, "revision_count": 2}) is True
    assert should_retry({"critic_passed": False, "revision_count": 3}) is False
    assert should_retry({"critic_passed": True, "revision_count": 0}) is False


def test_critic_action_types_stay_in_sync_with_approval_module():
    """
    Regression test: the benchmark run once caught a bug where
    'delete_resource' was a valid action in approval.py's risk scoring
    but rejected by the critic as an 'unknown action type' -- meaning
    the graph could never actually reach the approval gate for that
    action. Every action type approval.py knows about must also be
    accepted by the critic.
    """
    from app.approval import ALWAYS_REVIEW_ACTIONS
    from app.agents.critic import VALID_ACTION_TYPES

    assert ALWAYS_REVIEW_ACTIONS.issubset(VALID_ACTION_TYPES)


def test_critic_blocks_action_body_containing_secret(tmp_path, monkeypatch):
    """
    Security regression test: an action body that looks like it contains
    a credential (real, hallucinated, or planted via prompt injection)
    must never pass the critic, since a passing action can go out publicly
    (GitHub comment, Slack message).
    """
    tracker = _tracker(tmp_path, monkeypatch, "critic_secret.db")
    state = {
        "proposed_action": {
            "type": "post_comment",
            "body": "Fixed it, here's the working config: AKIAABCDEFGHIJKLMNOP",
        },
        "revision_count": 0,
        "trace": [],
    }
    result = critic_node(state, tracker)
    assert result["critic_passed"] is False
    assert "secret" in result["critic_feedback"].lower()
