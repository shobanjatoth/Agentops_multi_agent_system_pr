from app.approval import ApprovalStore, needs_human_approval, score_risk


def test_score_risk_low_for_comment():
    action = {"type": "post_comment", "target": "myorg/myapp#101"}
    assert score_risk(action) < 0.3


def test_score_risk_high_for_merge():
    action = {"type": "merge_pr", "target": "myorg/myapp"}
    assert score_risk(action) > 0.7


def test_score_risk_bumped_for_prod_target():
    low_risk = score_risk({"type": "post_comment", "target": "staging"})
    high_risk = score_risk({"type": "post_comment", "target": "prod-main"})
    assert high_risk > low_risk


def test_always_review_actions_require_approval_even_if_low_scored():
    assert needs_human_approval({"type": "merge_pr", "target": "x"}) is True
    assert needs_human_approval({"type": "delete_resource", "target": "x"}) is True


def test_safe_action_does_not_require_approval():
    action = {"type": "notify_slack", "target": "#eng"}
    assert needs_human_approval(action, risk_score=0.1) is False


def test_approval_store_add_and_resolve():
    store = ApprovalStore()
    store.add("task-1", {"type": "open_pr"}, risk_score=0.5)
    assert "task-1" in store.pending()

    resolved = store.resolve("task-1", approved=True)
    assert resolved["action"]["type"] == "open_pr"
    assert "task-1" not in store.pending()
