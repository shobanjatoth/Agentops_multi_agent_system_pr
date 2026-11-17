# from app.graph import build_graph, build_tool_registry
# from app.eval_tracker import EvalTracker
# from app.llm import LLMResult


# def _tracker(tmp_path, monkeypatch, name="graph.db"):
#     monkeypatch.setenv("AGENTOPS_DB_PATH", str(tmp_path / name))
#     monkeypatch.delenv("GITHUB_TOKEN", raising=False)
#     monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
#     import importlib

#     import app.eval_tracker as et
#     importlib.reload(et)
#     return et.EvalTracker(task_id="graph-test")


# def _base_state(description, repo="myorg/myapp"):
#     return {
#         "task_id": "graph-test", "description": description, "repo": repo,
#         "status": "pending", "trace": [], "tool_calls": [],
#         "context_snippets": [], "revision_count": 0,
#     }


# class FakeLLMSafe:
#     def complete(self, system, prompt, max_tokens=1024, temperature=0.2):
#         if "exactly ONE next action" in system:
#             return LLMResult(
#                 text='{"type": "notify_slack", "target": "#eng", "body": "FYI, looking into this."}',
#                 input_tokens=80, output_tokens=25, latency_ms=5.0,
#             )
#         return LLMResult(text="bug", input_tokens=10, output_tokens=1, latency_ms=2.0)


# class FakeLLMRisky:
#     def complete(self, system, prompt, max_tokens=1024, temperature=0.2):
#         if "exactly ONE next action" in system:
#             return LLMResult(
#                 text='{"type": "merge_pr", "target": "myorg/myapp-main", "body": "Merging hotfix."}',
#                 input_tokens=80, output_tokens=25, latency_ms=5.0,
#             )
#         return LLMResult(text="bug", input_tokens=10, output_tokens=1, latency_ms=2.0)


# class FakeLLMAlwaysInvalidJSON:
#     def complete(self, system, prompt, max_tokens=1024, temperature=0.2):
#         if "exactly ONE next action" in system:
#             return LLMResult(text="not json, sorry", input_tokens=80, output_tokens=25, latency_ms=5.0)
#         return LLMResult(text="bug", input_tokens=10, output_tokens=1, latency_ms=2.0)


# class FakeLLMAlwaysInvalidJSON_BannedPhrase:
#     """Returns a syntactically valid action that the critic will reject every time (banned phrase)."""

#     def complete(self, system, prompt, max_tokens=1024, temperature=0.2):
#         if "exactly ONE next action" in system:
#             return LLMResult(
#                 text='{"type": "post_comment", "target": "org/app", "body": "I cannot determine a fix."}',
#                 input_tokens=80, output_tokens=25, latency_ms=5.0,
#             )
#         return LLMResult(text="bug", input_tokens=10, output_tokens=1, latency_ms=2.0)


# def test_full_graph_low_risk_auto_completes(tmp_path, monkeypatch):
#     tracker = _tracker(tmp_path, monkeypatch, "g1.db")
#     graph = build_graph(tracker=tracker, llm=FakeLLMSafe(), tools=build_tool_registry())
#     final = graph.invoke(_base_state("Users report login fails on mobile Safari"))
#     assert final["status"] == "done"
#     assert final["requires_human_approval"] is False


# def test_full_graph_high_risk_awaits_approval(tmp_path, monkeypatch):
#     tracker = _tracker(tmp_path, monkeypatch, "g2.db")
#     graph = build_graph(tracker=tracker, llm=FakeLLMRisky(), tools=build_tool_registry())
#     final = graph.invoke(_base_state("Critical production outage, all users affected"))
#     assert final["status"] == "awaiting_approval"
#     assert final["requires_human_approval"] is True
#     assert final["proposed_action"]["type"] == "merge_pr"


# def test_full_graph_fallback_action_still_passes_critic(tmp_path, monkeypatch):
#     # invalid JSON from the action LLM triggers the deterministic fallback
#     # action, which is valid enough to pass the critic on the first try.
#     tracker = _tracker(tmp_path, monkeypatch, "g3.db")
#     graph = build_graph(tracker=tracker, llm=FakeLLMAlwaysInvalidJSON(), tools=build_tool_registry())
#     final = graph.invoke(_base_state("Something is broken with checkout"))
#     assert final["proposed_action"]["type"] == "post_comment"
#     assert final["status"] in ("done", "awaiting_approval")


# def test_graph_logs_every_node_to_tracker(tmp_path, monkeypatch):
#     tracker = _tracker(tmp_path, monkeypatch, "g4.db")
#     graph = build_graph(tracker=tracker, llm=FakeLLMSafe(), tools=build_tool_registry())
#     graph.invoke(_base_state("Feature request: add dark mode toggle"))
#     summary = tracker.task_summary()
#     node_names = {step["node"] for step in summary["steps"]}
#     assert {"triage", "research", "action", "critic"}.issubset(node_names)


# def test_full_graph_marks_status_failed_after_retry_exhaustion(tmp_path, monkeypatch):
#     """
#     Regression test: the benchmark script once caught a bug where a task
#     that exhausted all 3 critic retries was left at status='in_progress'
#     forever instead of being marked 'failed'. This locks in the fix.
#     """
#     tracker = _tracker(tmp_path, monkeypatch, "g5.db")
#     graph = build_graph(tracker=tracker, llm=FakeLLMAlwaysInvalidJSON_BannedPhrase(), tools=build_tool_registry())
#     final = graph.invoke(_base_state("Vague ticket with no reproducible detail"))
#     assert final["status"] == "failed"
#     assert final["revision_count"] == 3
#     assert final["final_result"] is not None












from app.graph import build_graph, build_tool_registry
from app.llm import LLMResult


def _tracker(tmp_path, monkeypatch, name="graph.db"):
    monkeypatch.setenv(
        "AGENTOPS_DB_PATH",
        str(tmp_path / name),
    )
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)

    import importlib
    import app.eval_tracker as et

    importlib.reload(et)

    return et.EvalTracker(task_id="graph-test")


def _base_state(description, repo="myorg/myapp"):
    return {
        "task_id": "graph-test",
        "description": description,
        "repo": repo,
        "status": "pending",
        "trace": [],
        "tool_calls": [],
        "context_snippets": [],
        "revision_count": 0,
    }


class FakeLLMSafe:
    def complete(
        self,
        system,
        prompt,
        max_tokens=1024,
        temperature=0.2,
    ):
        if "exactly ONE" in system:
            return LLMResult(
                text=(
                    '{"type": "notify_slack", '
                    '"target": "#eng", '
                    '"body": "FYI, looking into this."}'
                ),
                input_tokens=80,
                output_tokens=25,
                latency_ms=5.0,
            )

        return LLMResult(
            text="bug",
            input_tokens=10,
            output_tokens=1,
            latency_ms=2.0,
        )


class FakeLLMRisky:
    def complete(
        self,
        system,
        prompt,
        max_tokens=1024,
        temperature=0.2,
    ):
        if "exactly ONE" in system:
            return LLMResult(
                text=(
                    '{"type": "open_pr", '
                    '"repo": "myorg/myapp", '
                    '"title": "Emergency hotfix", '
                    '"body": "Proposed production hotfix.", '
                    '"head": "hotfix-branch", '
                    '"base": "main"}'
                ),
                input_tokens=80,
                output_tokens=25,
                latency_ms=5.0,
            )

        return LLMResult(
            text="bug",
            input_tokens=10,
            output_tokens=1,
            latency_ms=2.0,
        )


class FakeLLMAlwaysInvalidJSON:
    def complete(
        self,
        system,
        prompt,
        max_tokens=1024,
        temperature=0.2,
    ):
        if "exactly ONE" in system:
            return LLMResult(
                text="not json, sorry",
                input_tokens=80,
                output_tokens=25,
                latency_ms=5.0,
            )

        return LLMResult(
            text="bug",
            input_tokens=10,
            output_tokens=1,
            latency_ms=2.0,
        )


class FakeLLMAlwaysInvalidJSON_BannedPhrase:
    """Returns a valid action with a phrase the critic must reject."""

    def complete(
        self,
        system,
        prompt,
        max_tokens=1024,
        temperature=0.2,
    ):
        if "exactly ONE" in system:
            return LLMResult(
                text=(
                    '{"type": "post_comment", '
                    '"target": "org/app", '
                    '"body": "I cannot determine a fix."}'
                ),
                input_tokens=80,
                output_tokens=25,
                latency_ms=5.0,
            )

        return LLMResult(
            text="bug",
            input_tokens=10,
            output_tokens=1,
            latency_ms=2.0,
        )


def test_full_graph_low_risk_auto_completes(
    tmp_path,
    monkeypatch,
):
    tracker = _tracker(tmp_path, monkeypatch, "g1.db")

    graph = build_graph(
        tracker=tracker,
        llm=FakeLLMSafe(),
        tools=build_tool_registry(mocked=True),
    )

    final = graph.invoke(
        _base_state("Users report login fails on mobile Safari")
    )

    assert final["status"] == "done"
    assert final["requires_human_approval"] is False


def test_full_graph_high_risk_awaits_approval(
    tmp_path,
    monkeypatch,
):
    tracker = _tracker(tmp_path, monkeypatch, "g2.db")

    graph = build_graph(
        tracker=tracker,
        llm=FakeLLMRisky(),
        tools=build_tool_registry(mocked=True),
    )

    final = graph.invoke(
        _base_state("Critical production outage, all users affected")
    )

    assert final["status"] == "awaiting_approval"
    assert final["requires_human_approval"] is True
    assert final["proposed_action"]["type"] == "open_pr"


def test_full_graph_fallback_action_still_passes_critic(
    tmp_path,
    monkeypatch,
):
    tracker = _tracker(tmp_path, monkeypatch, "g3.db")

    graph = build_graph(
        tracker=tracker,
        llm=FakeLLMAlwaysInvalidJSON(),
        tools=build_tool_registry(mocked=True),
    )

    final = graph.invoke(
        _base_state("Something is broken with checkout")
    )

    assert final["proposed_action"]["type"] == "post_comment"
    assert final["status"] in ("done", "awaiting_approval")


def test_graph_logs_every_node_to_tracker(
    tmp_path,
    monkeypatch,
):
    tracker = _tracker(tmp_path, monkeypatch, "g4.db")

    graph = build_graph(
        tracker=tracker,
        llm=FakeLLMSafe(),
        tools=build_tool_registry(mocked=True),
    )

    graph.invoke(
        _base_state("Feature request: add dark mode toggle")
    )

    summary = tracker.task_summary()

    node_names = {
        step["node"]
        for step in summary["steps"]
    }

    assert {
        "triage",
        "research",
        "action",
        "critic",
    }.issubset(node_names)


def test_full_graph_marks_status_failed_after_retry_exhaustion(
    tmp_path,
    monkeypatch,
):
    tracker = _tracker(tmp_path, monkeypatch, "g5.db")

    graph = build_graph(
        tracker=tracker,
        llm=FakeLLMAlwaysInvalidJSON_BannedPhrase(),
        tools=build_tool_registry(mocked=True),
    )

    final = graph.invoke(
        _base_state("Vague ticket with no reproducible detail")
    )

    assert final["status"] == "failed"
    assert final["revision_count"] == 3
    assert final["final_result"] is not None
