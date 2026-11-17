
# from __future__ import annotations

# import re
# from typing import Any

# from app.eval_tracker import EvalTracker
# from app.tools.base import ToolRegistry


# REPO_PATTERN = re.compile(
#     r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
# )

# TARGET_PATTERN = re.compile(
#     r"^([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#([1-9][0-9]*)$"
# )

# SUPPORTED_ACTIONS = {
#     "post_comment",
#     "open_pr",
#     "notify_slack",
# }


# def _record(
#     tracker: EvalTracker,
#     node: str,
#     action: dict,
#     result: dict,
#     latency_ms: float = 0.0,
#     passed: bool = True,
# ) -> None:
#     tracker.log_node(
#         node=node,
#         input_summary=str(action),
#         output_summary=str(result),
#         latency_ms=latency_ms,
#         passed=passed,
#     )


# def execute_action(
#     action: dict[str, Any],
#     repo: str | None,
#     tools: ToolRegistry,
#     tracker: EvalTracker,
# ) -> dict:
#     """
#     Execute one supported action.

#     Unsupported or invalid actions are blocked.
#     Mock responses are reported separately from real execution.
#     """

#     action_type = action.get("type")
#     body = action.get("body")

#     if action_type not in SUPPORTED_ACTIONS:
#         result = {
#             "executed": False,
#             "success": False,
#             "execution_status": "unsupported",
#             "message": f"Action '{action_type}' is not supported.",
#         }

#         _record(
#             tracker,
#             "executor.blocked",
#             action,
#             result,
#             passed=False,
#         )
#         return result

#     if not isinstance(body, str) or not body.strip():
#         result = {
#             "executed": False,
#             "success": False,
#             "execution_status": "invalid",
#             "message": "Action body is missing or empty.",
#         }

#         _record(
#             tracker,
#             "executor.blocked",
#             action,
#             result,
#             passed=False,
#         )
#         return result

#     try:
#         if action_type == "post_comment":
#             target = action.get("target", "")

#             target_match = (
#                 TARGET_PATTERN.fullmatch(target)
#                 if isinstance(target, str)
#                 else None
#             )

#             action_repo = action.get("repo") or repo
#             issue_number = action.get("issue_number")

#             if target_match:
#                 action_repo = target_match.group(1)
#                 issue_number = int(target_match.group(2))

#             if (
#                 not isinstance(action_repo, str)
#                 or not REPO_PATTERN.fullmatch(action_repo)
#             ):
#                 raise ValueError(
#                     "A valid repository is required for post_comment."
#                 )

#             if (
#                 not isinstance(issue_number, int)
#                 or isinstance(issue_number, bool)
#                 or issue_number <= 0
#             ):
#                 raise ValueError(
#                     "A positive issue_number is required. "
#                     "Use target='owner/repository#123'."
#                 )

#             tool = tools.get("github")

#             tool_result = tool.call(
#                 action="post_comment",
#                 repo=action_repo,
#                 issue_number=issue_number,
#                 body=body,
#             )

#         elif action_type == "open_pr":
#             action_repo = action.get("repo") or repo
#             title = action.get("title")
#             head = action.get("head")
#             base = action.get("base", "main")

#             if (
#                 not isinstance(action_repo, str)
#                 or not REPO_PATTERN.fullmatch(action_repo)
#             ):
#                 raise ValueError(
#                     "A valid repository is required for open_pr."
#                 )

#             if not isinstance(title, str) or not title.strip():
#                 raise ValueError("A pull request title is required.")

#             if not isinstance(head, str) or not head.strip():
#                 raise ValueError("A head branch is required.")

#             if not isinstance(base, str) or not base.strip():
#                 raise ValueError("A base branch is required.")

#             tool = tools.get("github")

#             tool_result = tool.call(
#                 action="open_pr",
#                 repo=action_repo,
#                 title=title,
#                 body=body,
#                 head=head,
#                 base=base,
#             )

#         else:
#             channel = action.get("target", "#agentops")

#             if not isinstance(channel, str) or not channel.strip():
#                 raise ValueError("Slack channel label is invalid.")

#             tool = tools.get("slack")

#             tool_result = tool.call(
#                 action="notify",
#                 message=body,
#                 channel=channel,
#             )

#         output = tool_result.output
#         mocked = tool_result.mocked

#         success = bool(
#             output.get("posted")
#             or output.get("opened")
#             or output.get("sent")
#         )

#         execution_status = (
#             "mocked" if mocked and success
#             else "succeeded" if success
#             else "failed"
#         )

#         result = {
#             "executed": success and not mocked,
#             "success": success,
#             "mocked": mocked,
#             "execution_status": execution_status,
#             "tool": tool.name,
#             "output": output,
#             "latency_ms": round(tool_result.latency_ms, 2),
#         }

#         _record(
#             tracker,
#             f"executor.{tool.name}.{action_type}",
#             action,
#             result,
#             latency_ms=tool_result.latency_ms,
#             passed=success,
#         )

#         return result

#     except Exception as exc:
#         result = {
#             "executed": False,
#             "success": False,
#             "execution_status": "failed",
#             "message": str(exc),
#         }

#         _record(
#             tracker,
#             "executor.failed",
#             action,
#             result,
#             passed=False,
#         )

#         return result













from __future__ import annotations

import re
from typing import Any

from app.eval_tracker import EvalTracker
from app.tools.base import ToolRegistry


REPO_PATTERN = re.compile(
    r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
)

TARGET_PATTERN = re.compile(
    r"^([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#([1-9][0-9]*)$"
)

SUPPORTED_ACTIONS = {
    "post_comment",
    "open_pr",
    "notify_slack",
}


def _record(
    tracker: EvalTracker,
    node: str,
    action: dict,
    result: dict,
    latency_ms: float = 0.0,
    passed: bool = True,
) -> None:
    tracker.log_node(
        node=node,
        input_summary=str(action),
        output_summary=str(result),
        latency_ms=latency_ms,
        passed=passed,
    )


def _notify_pr_created(
    action: dict,
    action_repo: str,
    pr_response: dict,
    tools: ToolRegistry,
    tracker: EvalTracker,
) -> dict:
    """Send a Slack notification after a real PR is created."""

    pr_number = pr_response.get("number")
    pr_url = pr_response.get("html_url")
    title = action.get("title", "Untitled PR")

    if not pr_number or not pr_url:
        result = {
            "success": False,
            "status": "missing_pr_details",
            "message": "GitHub response did not contain PR number or URL.",
        }

        _record(
            tracker,
            "executor.slack.notification",
            action,
            result,
            passed=False,
        )
        return result

    message = (
        "GitHub pull request created successfully!\n"
        f"Repository: {action_repo}\n"
        f"PR: #{pr_number}\n"
        f"Title: {title}\n"
        f"URL: {pr_url}"
    )

    slack_action = {
        "type": "notify_slack",
        "target": "#agentops",
        "body": message,
    }

    try:
        slack_tool = tools.get("slack")

        slack_result = slack_tool.call(
            action="notify",
            message=message,
            channel="#agentops",
        )

        output = slack_result.output
        success = bool(output.get("sent"))

        result = {
            "success": success,
            "mocked": slack_result.mocked,
            "execution_status": (
                "mocked" if slack_result.mocked and success
                else "succeeded" if success
                else "failed"
            ),
            "output": output,
            "latency_ms": round(slack_result.latency_ms, 2),
        }

        _record(
            tracker,
            "executor.slack.notification",
            slack_action,
            result,
            latency_ms=slack_result.latency_ms,
            passed=success,
        )

        return result

    except Exception as exc:
        result = {
            "success": False,
            "execution_status": "failed",
            "message": str(exc),
        }

        _record(
            tracker,
            "executor.slack.notification",
            slack_action,
            result,
            passed=False,
        )

        return result


def execute_action(
    action: dict[str, Any],
    repo: str | None,
    tools: ToolRegistry,
    tracker: EvalTracker,
) -> dict:
    """
    Execute one supported action.

    After a successful real GitHub PR creation,
    automatically send a Slack notification.

    GitHub success is preserved even if Slack fails.
    """

    action_type = action.get("type")
    body = action.get("body")

    if action_type not in SUPPORTED_ACTIONS:
        result = {
            "executed": False,
            "success": False,
            "execution_status": "unsupported",
            "message": f"Action '{action_type}' is not supported.",
        }

        _record(
            tracker,
            "executor.blocked",
            action,
            result,
            passed=False,
        )
        return result

    if not isinstance(body, str) or not body.strip():
        result = {
            "executed": False,
            "success": False,
            "execution_status": "invalid",
            "message": "Action body is missing or empty.",
        }

        _record(
            tracker,
            "executor.blocked",
            action,
            result,
            passed=False,
        )
        return result

    try:
        if action_type == "post_comment":
            target = action.get("target", "")

            target_match = (
                TARGET_PATTERN.fullmatch(target)
                if isinstance(target, str)
                else None
            )

            action_repo = action.get("repo") or repo
            issue_number = action.get("issue_number")

            if target_match:
                action_repo = target_match.group(1)
                issue_number = int(target_match.group(2))

            if (
                not isinstance(action_repo, str)
                or not REPO_PATTERN.fullmatch(action_repo)
            ):
                raise ValueError(
                    "A valid repository is required for post_comment."
                )

            if (
                not isinstance(issue_number, int)
                or isinstance(issue_number, bool)
                or issue_number <= 0
            ):
                raise ValueError(
                    "A positive issue_number is required. "
                    "Use target='owner/repository#123'."
                )

            tool = tools.get("github")

            tool_result = tool.call(
                action="post_comment",
                repo=action_repo,
                issue_number=issue_number,
                body=body,
            )

        elif action_type == "open_pr":
            action_repo = action.get("repo") or repo
            title = action.get("title")
            head = action.get("head")
            base = action.get("base", "main")

            if (
                not isinstance(action_repo, str)
                or not REPO_PATTERN.fullmatch(action_repo)
            ):
                raise ValueError(
                    "A valid repository is required for open_pr."
                )

            if not isinstance(title, str) or not title.strip():
                raise ValueError("A pull request title is required.")

            if not isinstance(head, str) or not head.strip():
                raise ValueError("A head branch is required.")

            if not isinstance(base, str) or not base.strip():
                raise ValueError("A base branch is required.")

            tool = tools.get("github")

            tool_result = tool.call(
                action="open_pr",
                repo=action_repo,
                title=title,
                body=body,
                head=head,
                base=base,
            )

        else:
            channel = action.get("target", "#agentops")

            if not isinstance(channel, str) or not channel.strip():
                raise ValueError("Slack channel label is invalid.")

            tool = tools.get("slack")

            tool_result = tool.call(
                action="notify",
                message=body,
                channel=channel,
            )

        output = tool_result.output
        mocked = tool_result.mocked

        success = bool(
            output.get("posted")
            or output.get("opened")
            or output.get("sent")
        )

        execution_status = (
            "mocked" if mocked and success
            else "succeeded" if success
            else "failed"
        )

        result = {
            "executed": success and not mocked,
            "success": success,
            "mocked": mocked,
            "execution_status": execution_status,
            "tool": tool.name,
            "output": output,
            "latency_ms": round(tool_result.latency_ms, 2),
        }

        _record(
            tracker,
            f"executor.{tool.name}.{action_type}",
            action,
            result,
            latency_ms=tool_result.latency_ms,
            passed=success,
        )

        # Automatic Slack notification after a real GitHub PR.
        if action_type == "open_pr" and success and not mocked:
            pr_response = output.get("response", {})

            notification = _notify_pr_created(
                action=action,
                action_repo=action_repo,
                pr_response=pr_response,
                tools=tools,
                tracker=tracker,
            )

            result["notification"] = notification
            result["notification_success"] = notification["success"]

            if not notification["success"]:
                result["execution_status"] = (
                    "succeeded_with_notification_failure"
                )

        elif action_type == "open_pr" and mocked and success:
            result["notification"] = {
                "success": False,
                "execution_status": "skipped_mocked",
                "message": "Slack notification skipped for mocked PR.",
            }
            result["notification_success"] = False

        return result

    except Exception as exc:
        result = {
            "executed": False,
            "success": False,
            "execution_status": "failed",
            "message": str(exc),
        }

        _record(
            tracker,
            "executor.failed",
            action,
            result,
            passed=False,
        )

        return result
