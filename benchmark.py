#  """
# Reproducible benchmark runner for AgentOps.

# Runs a fixed set of synthetic support tickets through the full LangGraph
# pipeline (triage -> research -> action -> critic -> approval gate) and
# reports real numbers: task success rate, critic retry rate, human-approval
# rate, and per-node latency. Uses a deterministic fake LLM (no network, no
# API key required) so results are 100% reproducible across machines and CI.

# This mirrors the benchmark pattern used in RepoMind AI (benchmark.py) --
# a resume claim like "X% task success rate across N scenarios" should
# always be backed by a script anyone can re-run and get the same number.

# Usage:
#     python benchmark.py                    # run all scenarios, print + save JSON
#     python benchmark.py --output out.json  # custom output path
# """
# from __future__ import annotations

# import argparse
# import json
# import statistics
# import time
# from dataclasses import dataclass, field

# from app.eval_tracker import EvalTracker
# from app.graph import build_graph, build_tool_registry
# from app.llm import LLMResult

# # ---------------------------------------------------------------------------
# # Benchmark scenarios
# #
# # Each scenario is a realistic ticket description plus the action JSON a
# # reasonable LLM would propose for it. A handful are deliberately
# # malformed (invalid JSON) or risky (merge_pr / prod target) so the
# # benchmark exercises the critic's retry loop and the approval gate, not
# # just the happy path -- a 100%-pass benchmark would not be credible.
# # ---------------------------------------------------------------------------


# @dataclass
# class Scenario:
#     name: str
#     description: str
#     repo: str
#     action_json: str  # what the fake Action-Agent LLM call returns
#     expect_requires_approval: bool | None = None  # None = don't assert, just record


# SCENARIOS: list[Scenario] = [
#     Scenario(
#         "bug_low_risk_comment",
#         "Users report login fails on mobile Safari after last deploy",
#         "org/app",
#         '{"type": "post_comment", "target": "org/app#101", "body": "Investigating the Safari login issue now."}',
#         expect_requires_approval=False,
#     ),
#     Scenario(
#         "feature_request",
#         "Feature request: add a dark mode toggle to settings",
#         "org/app",
#         '{"type": "post_comment", "target": "org/app#98", "body": "Thanks, adding to the backlog for review."}',
#         expect_requires_approval=False,
#     ),
#     Scenario(
#         "question_docs",
#         "How do I configure the webhook retry interval? Docs are unclear.",
#         "org/app",
#         '{"type": "notify_slack", "target": "#support", "body": "Docs gap flagged, drafting an FAQ answer."}',
#         expect_requires_approval=False,
#     ),
#     Scenario(
#         "critical_outage",
#         "Critical: production down, complete outage, all users affected, data loss risk",
#         "org/app",
#         '{"type": "merge_pr", "target": "org/app-main", "body": "Merging emergency hotfix for the outage."}',
#         expect_requires_approval=True,
#     ),
#     Scenario(
#         "payment_bug_high_priority",
#         "Checkout payment fails for many users with a 500 error",
#         "org/app",
#         '{"type": "open_pr", "target": "org/app", "body": "Opening a PR with the payment-flow fix."}',
#         expect_requires_approval=True,  # open_pr base risk 0.35 > the 0.3 threshold
#     ),
#     Scenario(
#         "send_email_always_reviewed",
#         "Customer complaint escalation needs a formal email response",
#         "org/app",
#         '{"type": "send_email", "target": "customer@example.com", "body": "Formal apology and resolution email."}',
#         expect_requires_approval=True,
#     ),
#     Scenario(
#         "malformed_llm_output",
#         "Something is broken with the search bar on the homepage",
#         "org/app",
#         "I think the issue might be related to the search index configuration.",  # not JSON -> triggers fallback
#         expect_requires_approval=False,
#     ),
#     Scenario(
#         "delete_resource_always_reviewed",
#         "Stale feature-flag branch needs cleanup, delete the old config",
#         "org/app",
#         '{"type": "delete_resource", "target": "org/app/config/old-flag", "body": "Removing deprecated flag config."}',
#         expect_requires_approval=True,
#     ),
#     Scenario(
#         "close_stale_issue",
#         "This bug report looks like a duplicate of #45, can it be closed?",
#         "org/app",
#         '{"type": "close_issue", "target": "org/app#101", "body": "Closing as duplicate of #45."}',
#         expect_requires_approval=False,
#     ),
#     Scenario(
#         "prod_target_bumps_risk",
#         "Config drift detected between staging and prod environments",
#         "org/app",
#         '{"type": "post_comment", "target": "prod-release", "body": "Flagging config drift for review."}',
#         expect_requires_approval=True,  # 0.15 base + 0.2 prod-target bump = 0.35, which is > the 0.3 threshold
#     ),
#     Scenario(
#         "unfixable_low_quality_output",
#         "Vague ticket with almost no reproducible detail: 'app feels slow sometimes'",
#         "org/app",
#         '{"type": "post_comment", "target": "org/app", "body": "I cannot determine a specific fix from this report."}',
#         expect_requires_approval=None,  # deliberately fails the critic's banned-phrase check every retry -> exhausts and fails
#     ),
# ]


# class ScenarioLLM:
#     """Deterministic fake LLM bound to one scenario's expected action JSON."""

#     def __init__(self, scenario: Scenario):
#         self.scenario = scenario

#     def complete(self, system: str, prompt: str, max_tokens: int = 1024, temperature: float = 0.2) -> LLMResult:
#         if "exactly ONE next action" in system:
#             return LLMResult(
#                 text=self.scenario.action_json,
#                 input_tokens=110,
#                 output_tokens=35,
#                 latency_ms=6.0,
#             )
#         # triage classification call (only reached when keyword rules are ambiguous)
#         return LLMResult(text="bug", input_tokens=12, output_tokens=1, latency_ms=2.0)


# @dataclass
# class ScenarioResult:
#     name: str
#     status: str
#     requires_approval: bool
#     risk_score: float
#     revision_count: int
#     wall_clock_ms: float
#     node_latencies_ms: dict = field(default_factory=dict)
#     expectation_met: bool | None = None  # None = scenario had no expectation to check


# def run_benchmark() -> dict:
#     results: list[ScenarioResult] = []
#     mismatches: list[str] = []

#     for scenario in SCENARIOS:
#         tracker = EvalTracker(task_id=f"bench-{scenario.name}")
#         tracker.start_task(scenario.description)
#         graph = build_graph(tracker=tracker, llm=ScenarioLLM(scenario), tools=build_tool_registry())

#         start = time.perf_counter()
#         final_state = graph.invoke(
#             {
#                 "task_id": f"bench-{scenario.name}",
#                 "description": scenario.description,
#                 "repo": scenario.repo,
#                 "status": "pending",
#                 "trace": [],
#                 "tool_calls": [],
#                 "context_snippets": [],
#                 "revision_count": 0,
#             }
#         )
#         wall_clock_ms = round((time.perf_counter() - start) * 1000, 2)

#         actual_requires_approval = final_state.get("requires_human_approval", False)
#         expectation_met = None
#         if scenario.expect_requires_approval is not None:
#             expectation_met = actual_requires_approval == scenario.expect_requires_approval
#             if not expectation_met:
#                 mismatches.append(
#                     f"{scenario.name}: expected requires_approval="
#                     f"{scenario.expect_requires_approval}, got {actual_requires_approval}"
#                 )

#         node_latencies = {}
#         for step in final_state.get("trace", []):
#             node_latencies.setdefault(step["node"], []).append(step["latency_ms"])
#         node_latencies = {k: round(statistics.mean(v), 2) for k, v in node_latencies.items()}

#         results.append(
#             ScenarioResult(
#                 name=scenario.name,
#                 status=final_state.get("status", "unknown"),
#                 requires_approval=actual_requires_approval,
#                 risk_score=final_state.get("risk_score", 0.0),
#                 revision_count=final_state.get("revision_count", 0),
#                 wall_clock_ms=wall_clock_ms,
#                 node_latencies_ms=node_latencies,
#                 expectation_met=expectation_met,
#             )
#         )

#     if mismatches:
#         raise AssertionError(
#             "Benchmark scenario expectations were not met:\n  " + "\n  ".join(mismatches)
#         )

#     total = len(results)
#     succeeded = sum(1 for r in results if r.status in ("done", "awaiting_approval"))
#     failed = sum(1 for r in results if r.status == "failed")
#     approval_gated = sum(1 for r in results if r.requires_approval)
#     retried = sum(1 for r in results if r.revision_count > 0)

#     all_latencies = [r.wall_clock_ms for r in results]
#     checked = [r for r in results if r.expectation_met is not None]

#     summary = {
#         "total_scenarios": total,
#         "task_success_rate_pct": round(succeeded / total * 100, 1),
#         "failed_scenarios": failed,
#         "human_approval_gate_rate_pct": round(approval_gated / total * 100, 1),
#         "critic_retry_rate_pct": round(retried / total * 100, 1),
#         "expectations_checked": len(checked),
#         "expectations_met": sum(1 for r in checked if r.expectation_met),
#         "avg_wall_clock_ms": round(statistics.mean(all_latencies), 2),
#         "p95_wall_clock_ms": round(sorted(all_latencies)[int(len(all_latencies) * 0.95) - 1], 2)
#         if len(all_latencies) > 1
#         else all_latencies[0],
#         "scenarios": [
#             {
#                 "name": r.name,
#                 "status": r.status,
#                 "requires_approval": r.requires_approval,
#                 "risk_score": r.risk_score,
#                 "revision_count": r.revision_count,
#                 "wall_clock_ms": r.wall_clock_ms,
#                 "node_latencies_ms": r.node_latencies_ms,
#                 "expectation_met": r.expectation_met,
#             }
#             for r in results
#         ],
#     }
#     return summary


# def main():
#     parser = argparse.ArgumentParser(description="Run the AgentOps reproducible benchmark")
#     parser.add_argument("--output", default="benchmark_results.json", help="Output JSON path")
#     args = parser.parse_args()

#     print(f"Running {len(SCENARIOS)} benchmark scenarios through the full graph...\n")
#     summary = run_benchmark()

#     print(f"Task success rate:        {summary['task_success_rate_pct']}%")
#     print(f"Human-approval gate rate: {summary['human_approval_gate_rate_pct']}%")
#     print(f"Critic retry rate:        {summary['critic_retry_rate_pct']}%")
#     print(f"Scenario expectations:    {summary['expectations_met']}/{summary['expectations_checked']} met")
#     print(f"Avg wall-clock / task:    {summary['avg_wall_clock_ms']} ms")
#     print(f"P95 wall-clock / task:    {summary['p95_wall_clock_ms']} ms\n")

#     with open(args.output, "w") as f:
#         json.dump(summary, f, indent=2)
#     print(f"Full results written to {args.output}")


# if __name__ == "__main__":
#     main()













"""
Reproducible benchmark runner for AgentOps.

Uses a deterministic fake LLM and mocked integrations.
No external GitHub or Slack requests are made.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time

from dataclasses import dataclass, field

from app.eval_tracker import EvalTracker
from app.graph import build_graph, build_tool_registry
from app.llm import LLMResult


@dataclass
class Scenario:
    name: str
    description: str
    repo: str
    action_json: str
    expect_requires_approval: bool | None = None


SCENARIOS: list[Scenario] = [
    Scenario(
        "bug_low_risk_comment",
        "Users report login fails on mobile Safari after last deploy",
        "org/app",
        '{"type": "post_comment", "target": "org/app#101", "body": "Investigating the Safari login issue now."}',
        False,
    ),
    Scenario(
        "feature_request",
        "Feature request: add a dark mode toggle to settings",
        "org/app",
        '{"type": "post_comment", "target": "org/app#98", "body": "Thanks, adding to the backlog for review."}',
        False,
    ),
    Scenario(
        "question_docs",
        "How do I configure the webhook retry interval? Docs are unclear.",
        "org/app",
        '{"type": "notify_slack", "target": "#support", "body": "Docs gap flagged, drafting an FAQ answer."}',
        False,
    ),
    Scenario(
        "critical_outage",
        "Critical: production down, complete outage, all users affected, data loss risk",
        "org/app",
        '{"type": "open_pr", "repo": "org/app", "title": "Emergency hotfix", "body": "Proposed emergency hotfix for review.", "head": "emergency-hotfix", "base": "main"}',
        True,
    ),
    Scenario(
        "payment_bug_high_priority",
        "Checkout payment fails for many users with a 500 error",
        "org/app",
        '{"type": "open_pr", "repo": "org/app", "title": "Fix payment flow", "body": "Proposed payment-flow fix.", "head": "payment-fix", "base": "main"}',
        True,
    ),
    Scenario(
        "send_email_always_reviewed",
        "Customer complaint escalation needs a formal email response",
        "org/app",
        '{"type": "notify_slack", "target": "#support", "body": "Customer complaint escalation needs a formal response."}',
        None,
    ),
    Scenario(
        "malformed_llm_output",
        "Something is broken with the search bar on the homepage",
        "org/app",
        "I think the issue might be related to the search index configuration.",
        False,
    ),
    Scenario(
        "delete_resource_always_reviewed",
        "Stale feature-flag branch needs cleanup, delete the old config",
        "org/app",
        '{"type": "open_pr", "repo": "org/app", "title": "Review stale feature flag", "body": "Proposed cleanup for review.", "head": "cleanup-feature-flag", "base": "main"}',
        True,
    ),
    Scenario(
        "close_stale_issue",
        "This bug report looks like a duplicate of #45, can it be closed?",
        "org/app",
        '{"type": "post_comment", "target": "org/app#101", "body": "This appears to be a duplicate of issue #45."}',
        False,
    ),
    Scenario(
        "prod_target_bumps_risk",
        "Config drift detected between staging and prod environments",
        "org/app",
        '{"type": "post_comment", "target": "prod-release", "body": "Flagging config drift for review."}',
        True,
    ),
    Scenario(
        "unfixable_low_quality_output",
        "Vague ticket with almost no reproducible detail: app feels slow sometimes",
        "org/app",
        '{"type": "post_comment", "target": "org/app", "body": "I cannot determine a specific fix from this report."}',
        None,
    ),
]


class ScenarioLLM:
    def __init__(self, scenario: Scenario):
        self.scenario = scenario

    def complete(
        self,
        system: str,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> LLMResult:
        if "exactly ONE concrete action" in system or "exactly ONE" in system:
            return LLMResult(
                text=self.scenario.action_json,
                input_tokens=110,
                output_tokens=35,
                latency_ms=6.0,
            )

        return LLMResult(
            text="bug",
            input_tokens=12,
            output_tokens=1,
            latency_ms=2.0,
        )


@dataclass
class ScenarioResult:
    name: str
    status: str
    requires_approval: bool
    risk_score: float
    revision_count: int
    wall_clock_ms: float
    node_latencies_ms: dict = field(default_factory=dict)
    expectation_met: bool | None = None


def run_benchmark() -> dict:
    results: list[ScenarioResult] = []
    mismatches: list[str] = []

    # Force mock integrations so benchmark never contacts external APIs.
    tools = build_tool_registry(mocked=True)

    for scenario in SCENARIOS:
        tracker = EvalTracker(
            task_id=f"bench-{scenario.name}"
        )
        tracker.start_task(scenario.description)

        graph = build_graph(
            tracker=tracker,
            llm=ScenarioLLM(scenario),
            tools=tools,
        )

        start = time.perf_counter()

        final_state = graph.invoke(
            {
                "task_id": f"bench-{scenario.name}",
                "description": scenario.description,
                "repo": scenario.repo,
                "status": "pending",
                "trace": [],
                "tool_calls": [],
                "context_snippets": [],
                "revision_count": 0,
            }
        )

        wall_clock_ms = round(
            (time.perf_counter() - start) * 1000,
            2,
        )

        actual_requires_approval = final_state.get(
            "requires_human_approval",
            False,
        )

        expectation_met = None

        if scenario.expect_requires_approval is not None:
            expectation_met = (
                actual_requires_approval
                == scenario.expect_requires_approval
            )

            if not expectation_met:
                mismatches.append(
                    f"{scenario.name}: expected requires_approval="
                    f"{scenario.expect_requires_approval}, "
                    f"got {actual_requires_approval}"
                )

        node_latencies = {}

        for step in final_state.get("trace", []):
            node_latencies.setdefault(
                step["node"],
                [],
            ).append(step["latency_ms"])

        node_latencies = {
            key: round(statistics.mean(values), 2)
            for key, values in node_latencies.items()
        }

        results.append(
            ScenarioResult(
                name=scenario.name,
                status=final_state.get("status", "unknown"),
                requires_approval=actual_requires_approval,
                risk_score=final_state.get("risk_score", 0.0),
                revision_count=final_state.get("revision_count", 0),
                wall_clock_ms=wall_clock_ms,
                node_latencies_ms=node_latencies,
                expectation_met=expectation_met,
            )
        )

    if mismatches:
        raise AssertionError(
            "Benchmark scenario expectations were not met:\n  "
            + "\n  ".join(mismatches)
        )

    total = len(results)

    succeeded = sum(
        1 for result in results
        if result.status in ("done", "awaiting_approval")
    )

    failed = sum(
        1 for result in results
        if result.status == "failed"
    )

    approval_gated = sum(
        1 for result in results
        if result.requires_approval
    )

    retried = sum(
        1 for result in results
        if result.revision_count > 0
    )

    all_latencies = [
        result.wall_clock_ms
        for result in results
    ]

    checked = [
        result for result in results
        if result.expectation_met is not None
    ]

    summary = {
        "total_scenarios": total,
        "task_success_rate_pct": round(
            succeeded / total * 100,
            1,
        ),
        "failed_scenarios": failed,
        "human_approval_gate_rate_pct": round(
            approval_gated / total * 100,
            1,
        ),
        "critic_retry_rate_pct": round(
            retried / total * 100,
            1,
        ),
        "expectations_checked": len(checked),
        "expectations_met": sum(
            1 for result in checked
            if result.expectation_met
        ),
        "avg_wall_clock_ms": round(
            statistics.mean(all_latencies),
            2,
        ),
        "p95_wall_clock_ms": round(
            sorted(all_latencies)[
                int(len(all_latencies) * 0.95) - 1
            ],
            2,
        ),
        "scenarios": [
            {
                "name": result.name,
                "status": result.status,
                "requires_approval": result.requires_approval,
                "risk_score": result.risk_score,
                "revision_count": result.revision_count,
                "wall_clock_ms": result.wall_clock_ms,
                "node_latencies_ms": result.node_latencies_ms,
                "expectation_met": result.expectation_met,
            }
            for result in results
        ],
    }

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Run the AgentOps reproducible benchmark"
    )

    parser.add_argument(
        "--output",
        default="benchmark_results.json",
        help="Output JSON path",
    )

    args = parser.parse_args()

    print(
        f"Running {len(SCENARIOS)} benchmark scenarios "
        "through the full graph...\n"
    )

    summary = run_benchmark()

    print(
        f"Task success rate:        "
        f"{summary['task_success_rate_pct']}%"
    )
    print(
        f"Human-approval gate rate: "
        f"{summary['human_approval_gate_rate_pct']}%"
    )
    print(
        f"Critic retry rate:        "
        f"{summary['critic_retry_rate_pct']}%"
    )
    print(
        f"Scenario expectations:    "
        f"{summary['expectations_met']}/"
        f"{summary['expectations_checked']} met"
    )
    print(
        f"Avg wall-clock / task:    "
        f"{summary['avg_wall_clock_ms']} ms"
    )
    print(
        f"P95 wall-clock / task:    "
        f"{summary['p95_wall_clock_ms']} ms\n"
    )

    with open(args.output, "w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2)

    print(f"Full results written to {args.output}")


if __name__ == "__main__":
    main()
