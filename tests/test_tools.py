import pytest

from app.tools.base import ToolRegistry
from app.tools.github_tool import GitHubTool
from app.tools.slack_tool import SlackTool


def test_github_tool_mock_mode_list_issues(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    tool = GitHubTool()
    assert tool.is_mocked is True
    result = tool.call(action="list_issues", repo="myorg/myapp")
    assert "issues" in result.output
    assert len(result.output["issues"]) > 0


def test_github_tool_mock_mode_get_issue(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    tool = GitHubTool()
    result = tool.call(action="get_issue", repo="myorg/myapp", issue_number=101)
    assert result.output["issue"]["number"] == 101


def test_github_tool_rejects_invalid_repo_slug(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    tool = GitHubTool()
    with pytest.raises(ValueError, match="owner/repository"):
        tool.call(action="list_issues", repo="owner/repo/../../admin")


def test_slack_tool_mock_mode(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    tool = SlackTool()
    assert tool.is_mocked is True
    result = tool.call(action="notify", message="hello team")
    assert result.output["sent"] is True


def test_tool_registry_register_and_get():
    registry = ToolRegistry()
    registry.register(GitHubTool())
    registry.register(SlackTool())
    assert set(registry.names()) == {"github", "slack"}
    assert registry.get("github").name == "github"
