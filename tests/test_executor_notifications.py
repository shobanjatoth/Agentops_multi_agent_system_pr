
from unittest.mock import Mock

from app.executor import execute_action
from app.tools.base import ToolRegistry, ToolResult


def build_registry(github_result, slack_result=None, slack_error=None):
    registry = ToolRegistry()

    github = Mock()
    github.name = "github"
    github.call.return_value = github_result
    registry.register(github)

    slack = Mock()
    slack.name = "slack"

    if slack_error:
        slack.call.side_effect = slack_error
    else:
        slack.call.return_value = slack_result

    registry.register(slack)
    return registry, github, slack


def build_tracker():
    return Mock()


def pr_action():
    return {
        "type": "open_pr",
        "repo": "owner/repository",
        "title": "Test PR",
        "body": "Documentation update",
        "head": "feature/test",
        "base": "main",
    }


def test_successful_pr_sends_slack_notification():
    github_result = ToolResult(
        output={
            "opened": True,
            "response": {
                "number": 12,
                "html_url": "https://github.com/owner/repository/pull/12",
            },
        },
        latency_ms=100,
        mocked=False,
    )
    slack_result = ToolResult(
        output={"sent": True},
        latency_ms=50,
        mocked=False,
    )

    registry, _, slack = build_registry(github_result, slack_result)

    result = execute_action(pr_action(), None, registry, build_tracker())

    assert result["success"] is True
    assert result["executed"] is True
    assert result["notification_success"] is True

    slack.call.assert_called_once()
    message = slack.call.call_args.kwargs["message"]
    assert "owner/repository" in message
    assert "#12" in message
    assert "https://github.com/owner/repository/pull/12" in message


def test_failed_pr_does_not_send_slack():
    github_result = ToolResult(
        output={"opened": False},
        latency_ms=100,
        mocked=False,
    )
    registry, _, slack = build_registry(github_result)

    result = execute_action(pr_action(), None, registry, build_tracker())

    assert result["success"] is False
    slack.call.assert_not_called()


def test_slack_failure_preserves_pr_success():
    github_result = ToolResult(
        output={
            "opened": True,
            "response": {
                "number": 13,
                "html_url": "https://github.com/owner/repository/pull/13",
            },
        },
        latency_ms=100,
        mocked=False,
    )
    registry, _, _ = build_registry(
        github_result,
        slack_error=RuntimeError("Slack unavailable"),
    )

    result = execute_action(pr_action(), None, registry, build_tracker())

    assert result["success"] is True
    assert result["executed"] is True
    assert result["notification_success"] is False
    assert result["execution_status"] == "succeeded_with_notification_failure"


def test_mocked_pr_skips_slack_notification():
    github_result = ToolResult(
        output={"opened": True},
        latency_ms=0,
        mocked=True,
    )
    registry, _, slack = build_registry(github_result)

    result = execute_action(pr_action(), None, registry, build_tracker())

    assert result["success"] is True
    assert result["executed"] is False
    assert result["notification"]["execution_status"] == "skipped_mocked"
    slack.call.assert_not_called()
