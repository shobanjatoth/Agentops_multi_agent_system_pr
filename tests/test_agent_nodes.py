from app.agents.action import action_node
from app.agents.research import research_node
from app.eval_tracker import EvalTracker
from app.llm import LLMResult
from app.tools.base import ToolRegistry
from app.tools.github_tool import GitHubTool
from app.tools.slack_tool import SlackTool


class FakeActionLLM:
    def __init__(self, text, tokens=(50, 20)):
        self.text = text
        self.tokens = tokens

    def complete(self, system, prompt, max_tokens=1024, temperature=0.2):
        return LLMResult(
            text=self.text, input_tokens=self.tokens[0], output_tokens=self.tokens[1], latency_ms=4.0
        )


def _tracker(tmp_path, monkeypatch, name="node.db"):
    monkeypatch.setenv("AGENTOPS_DB_PATH", str(tmp_path / name))
    import importlib

    import app.eval_tracker as et
    importlib.reload(et)
    return et.EvalTracker(task_id="node-test")


def _registry():
    reg = ToolRegistry()
    reg.register(GitHubTool())
    reg.register(SlackTool())
    return reg


# ---- research_node ----

def test_research_node_finds_matching_issue(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    tracker = _tracker(tmp_path, monkeypatch)
    state = {
        "description": "Users report login fails on mobile Safari",
        "repo": "myorg/myapp",
        "trace": [],
        "tool_calls": [],
    }
    result = research_node(state, tracker, _registry())
    assert len(result["context_snippets"]) == 1
    assert "safari" in result["context_snippets"][0].lower() or "ios" in result["context_snippets"][0].lower()
    assert len(result["tool_calls"]) == 2  # list_issues + get_issue


def test_research_node_no_matching_issue(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    tracker = _tracker(tmp_path, monkeypatch, "node2.db")
    state = {
        "description": "Completely unrelated topic about billing invoices",
        "repo": "myorg/myapp",
        "trace": [],
        "tool_calls": [],
    }
    result = research_node(state, tracker, _registry())
    assert len(result["tool_calls"]) == 1  # only list_issues, no match found
    assert "no matching" in result["context_snippets"][0].lower()


def test_research_node_appends_to_existing_trace(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    tracker = _tracker(tmp_path, monkeypatch, "node3.db")
    state = {
        "description": "dark mode toggle request",
        "repo": "myorg/myapp",
        "trace": [{"node": "triage", "input_summary": "x", "output_summary": "y",
                    "latency_ms": 1.0, "input_tokens": 0, "output_tokens": 0,
                    "cost_usd": 0.0, "passed": True}],
        "tool_calls": [],
    }
    result = research_node(state, tracker, _registry())
    assert len(result["trace"]) == 2
    assert result["trace"][0]["node"] == "triage"
    assert result["trace"][1]["node"] == "research"


# ---- action_node ----

def test_action_node_parses_valid_json(tmp_path, monkeypatch):
    tracker = _tracker(tmp_path, monkeypatch, "action1.db")
    llm = FakeActionLLM('{"type": "post_comment", "target": "myorg/myapp#101", "body": "Looking into it."}')
    state = {
        "description": "login broken", "category": "bug", "priority": "high",
        "context_snippets": ["context here"], "trace": [],
    }
    result = action_node(state, tracker, llm)
    assert result["proposed_action"]["type"] == "post_comment"
    assert 0.0 <= result["risk_score"] <= 1.0


def test_action_node_falls_back_on_invalid_json(tmp_path, monkeypatch):
    tracker = _tracker(tmp_path, monkeypatch, "action2.db")
    llm = FakeActionLLM("this is not valid json at all")
    state = {
        "description": "login broken", "category": "bug", "priority": "high",
        "context_snippets": [], "trace": [],
    }
    result = action_node(state, tracker, llm)
    assert result["proposed_action"]["type"] == "post_comment"  # fallback action
    assert result["trace"][-1]["passed"] is False  # parse failure is logged


def test_action_node_risk_score_reflects_action_type(tmp_path, monkeypatch):
    tracker = _tracker(tmp_path, monkeypatch, "action3.db")
    llm = FakeActionLLM('{"type": "merge_pr", "target": "myorg/myapp", "body": "Merging fix."}')
    state = {"description": "urgent fix", "category": "bug", "priority": "critical",
              "context_snippets": [], "trace": []}
    result = action_node(state, tracker, llm)
    assert result["risk_score"] > 0.7  # merge_pr is inherently risky
