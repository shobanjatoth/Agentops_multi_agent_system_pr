# """
# Research Agent

# Pulls context via MCP-style tools (GitHub issue history, prior Slack
# discussion) before any action is proposed — this is what keeps the
# Action Agent grounded instead of hallucinating a fix for a bug it never
# actually looked at, the same "zero hallucination" principle used in the
# AI Legal Advisor / Career Copilot projects.

# Security note: issue bodies come from GitHub, which is untrusted input —
# anyone can open an issue. Before this content reaches the Action Agent's
# prompt, it's scanned for likely prompt-injection attempts (logged, not
# silently dropped) and fenced with wrap_untrusted() so the LLM is told
# explicitly never to treat it as instructions. See app/security.py.
# """
# from __future__ import annotations

# from app.eval_tracker import EvalTracker
# from app.security import detect_prompt_injection, wrap_untrusted
# from app.state import AgentState
# from app.tools.base import ToolRegistry


# def research_node(state: AgentState, tracker: EvalTracker, tools: ToolRegistry) -> AgentState:
#     repo = state.get("repo") or "unknown/repo"
#     github = tools.get("github")

#     total_latency = 0.0
#     tool_calls = []
#     snippets: list[str] = []
#     injection_flagged = False

#     issues_result = github.call(action="list_issues", repo=repo)
#     total_latency += issues_result.latency_ms
#     tool_calls.append(
#         {
#             "tool": "github.list_issues",
#             "input": {"repo": repo},
#             "output": issues_result.output,
#             "latency_ms": issues_result.latency_ms,
#         }
#     )

#     matching_issue = None
#     for issue in issues_result.output.get("issues", []):
#         if any(word in issue["title"].lower() for word in state["description"].lower().split()[:6]):
#             matching_issue = issue
#             break

#     if matching_issue:
#         detail = github.call(action="get_issue", repo=repo, issue_number=matching_issue["number"])
#         total_latency += detail.latency_ms
#         tool_calls.append(
#             {
#                 "tool": "github.get_issue",
#                 "input": {"repo": repo, "issue_number": matching_issue["number"]},
#                 "output": detail.output,
#                 "latency_ms": detail.latency_ms,
#             }
#         )
#         issue_body = detail.output["issue"]["body"]
#         is_suspicious, matched = detect_prompt_injection(issue_body)
#         if is_suspicious:
#             injection_flagged = True
#             tracker.log_node(
#                 node="research.security",
#                 input_summary=issue_body[:200],
#                 output_summary=f"possible prompt injection in GitHub issue body: {matched}",
#                 latency_ms=0.0,
#                 passed=False,
#             )
#         # Untrusted regardless of whether injection patterns matched -- it's
#         # external content either way, so it's always fenced, not just when
#         # something suspicious was found.
#         snippets.append(wrap_untrusted(issue_body, source="github_issue"))
#     else:
#         snippets.append("No matching prior issue found — this looks like a new report.")

#     tracker.log_node(
#         node="research",
#         input_summary=state["description"],
#         output_summary=f"{len(tool_calls)} tool call(s), {len(snippets)} context snippet(s)",
#         latency_ms=total_latency,
#         passed=True,
#     )

#     return {
#         **state,
#         "context_snippets": snippets,
#         "tool_calls": state.get("tool_calls", []) + tool_calls,
#         "injection_flagged": injection_flagged,
#         "trace": state.get("trace", [])
#         + [
#             {
#                 "node": "research",
#                 "input_summary": state["description"][:200],
#                 "output_summary": f"{len(tool_calls)} tool calls" + (" [injection flagged]" if injection_flagged else ""),
#                 "latency_ms": total_latency,
#                 "input_tokens": 0,
#                 "output_tokens": 0,
#                 "cost_usd": 0.0,
#                 "passed": True,
#             }
#         ],
#     }














"""
Research Agent

Pulls repository context when a valid repository is provided.
Skips GitHub research for general tasks without a repository.
External issue content is treated as untrusted input.
"""
from __future__ import annotations

from app.eval_tracker import EvalTracker
from app.security import detect_prompt_injection, wrap_untrusted
from app.state import AgentState
from app.tools.base import ToolRegistry


def research_node(
    state: AgentState,
    tracker: EvalTracker,
    tools: ToolRegistry,
) -> AgentState:
    repo = state.get("repo")

    total_latency = 0.0
    tool_calls = []
    snippets: list[str] = []
    injection_flagged = False

    if not repo:
        snippets.append(
            "No repository was provided. GitHub research was skipped."
        )
    else:
        github = tools.get("github")

        issues_result = github.call(
            action="list_issues",
            repo=repo,
        )
        total_latency += issues_result.latency_ms

        tool_calls.append(
            {
                "tool": "github.list_issues",
                "input": {"repo": repo},
                "output": issues_result.output,
                "latency_ms": issues_result.latency_ms,
            }
        )

        matching_issue = None

        for issue in issues_result.output.get("issues", []):
            if any(
                word in issue["title"].lower()
                for word in state["description"].lower().split()[:6]
            ):
                matching_issue = issue
                break

        if matching_issue:
            detail = github.call(
                action="get_issue",
                repo=repo,
                issue_number=matching_issue["number"],
            )
            total_latency += detail.latency_ms

            tool_calls.append(
                {
                    "tool": "github.get_issue",
                    "input": {
                        "repo": repo,
                        "issue_number": matching_issue["number"],
                    },
                    "output": detail.output,
                    "latency_ms": detail.latency_ms,
                }
            )

            issue_body = detail.output["issue"]["body"]
            is_suspicious, matched = detect_prompt_injection(issue_body)

            if is_suspicious:
                injection_flagged = True
                tracker.log_node(
                    node="research.security",
                    input_summary=issue_body[:200],
                    output_summary=(
                        f"possible prompt injection in GitHub issue body: {matched}"
                    ),
                    latency_ms=0.0,
                    passed=False,
                )

            snippets.append(
                wrap_untrusted(issue_body, source="github_issue")
            )
        else:
            snippets.append(
                "No matching prior issue found — this looks like a new report."
            )

    tracker.log_node(
        node="research",
        input_summary=state["description"],
        output_summary=(
            f"{len(tool_calls)} tool call(s), "
            f"{len(snippets)} context snippet(s)"
        ),
        latency_ms=total_latency,
        passed=True,
    )

    return {
        **state,
        "context_snippets": snippets,
        "tool_calls": state.get("tool_calls", []) + tool_calls,
        "injection_flagged": injection_flagged,
        "trace": state.get("trace", [])
        + [
            {
                "node": "research",
                "input_summary": state["description"][:200],
                "output_summary": (
                    f"{len(tool_calls)} tool calls"
                    + (" [injection flagged]" if injection_flagged else "")
                ),
                "latency_ms": total_latency,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "passed": True,
            }
        ],
    }
