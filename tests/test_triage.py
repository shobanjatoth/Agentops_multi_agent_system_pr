from app.agents.triage import triage_node
from app.eval_tracker import EvalTracker
from app.llm import LLMResult


class FakeLLMClient:
    def complete(self, system, prompt, max_tokens=1024, temperature=0.2):
        return LLMResult(text="question", input_tokens=20, output_tokens=1, latency_ms=5.0)


def _tracker(tmp_path, monkeypatch, name="triage.db"):
    monkeypatch.setenv("AGENTOPS_DB_PATH", str(tmp_path / name))
    import importlib

    import app.eval_tracker as et
    importlib.reload(et)
    return et.EvalTracker(task_id="triage-test")


def test_triage_keyword_match_no_llm_call(tmp_path, monkeypatch):
    tracker = _tracker(tmp_path, monkeypatch)
    state = {"description": "The app crashes with a 500 error on checkout", "trace": []}
    result = triage_node(state, tracker, llm=FakeLLMClient())
    assert result["category"] == "bug"
    assert result["priority"] in ("medium", "high", "critical")


def test_triage_falls_back_to_llm_when_ambiguous(tmp_path, monkeypatch):
    tracker = _tracker(tmp_path, monkeypatch, "triage2.db")
    state = {"description": "Something about the pricing page seems off", "trace": []}
    result = triage_node(state, tracker, llm=FakeLLMClient())
    assert result["category"] == "question"


def test_triage_priority_critical_for_outage(tmp_path, monkeypatch):
    tracker = _tracker(tmp_path, monkeypatch, "triage3.db")
    state = {"description": "Production down, complete outage, all users affected", "trace": []}
    result = triage_node(state, tracker, llm=FakeLLMClient())
    assert result["priority"] == "critical"
