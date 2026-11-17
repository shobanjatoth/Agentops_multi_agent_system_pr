"""
Lightweight observability layer.

Every agent node call gets logged here: which node ran, how long it took,
how many tokens it burned, what it cost, and whether it passed its own
validation. This is the difference between a "demo" agent and a system a
team can actually operate — you can answer "why did this fail" and
"what is this costing us per task" without reading logs by hand.

Deliberately built on SQLite (zero external dependency) so the whole
project runs with `pip install -r requirements.txt` and nothing else.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field

DB_PATH = os.getenv("AGENTOPS_DB_PATH", "./data/agentops.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS traces (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    node TEXT NOT NULL,
    input_summary TEXT,
    output_summary TEXT,
    latency_ms REAL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,
    passed INTEGER,
    created_at REAL
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    description TEXT,
    status TEXT,
    requires_human_approval INTEGER,
    approved INTEGER,
    created_at REAL,
    updated_at REAL
);
"""


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def timed():
    """Context manager yielding an object you can read `.ms` off of afterwards."""
    box = {"ms": 0.0}
    start = time.perf_counter()
    try:
        yield box
    finally:
        box["ms"] = (time.perf_counter() - start) * 1000


@dataclass
class EvalTracker:
    """One instance per task; call `.log_node(...)` after each agent runs."""

    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self):
        init_db()

    def start_task(self, description: str) -> None:
        with _connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO tasks "
                "(id, description, status, requires_human_approval, approved, created_at, updated_at) "
                "VALUES (?, ?, 'in_progress', 0, NULL, ?, ?)",
                (self.task_id, description, time.time(), time.time()),
            )

    def log_node(
        self,
        node: str,
        input_summary: str,
        output_summary: str,
        latency_ms: float,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        passed: bool = True,
    ) -> None:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO traces (id, task_id, node, input_summary, output_summary, "
                "latency_ms, input_tokens, output_tokens, cost_usd, passed, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    self.task_id,
                    node,
                    input_summary[:500],
                    output_summary[:500],
                    latency_ms,
                    input_tokens,
                    output_tokens,
                    cost_usd,
                    int(passed),
                    time.time(),
                ),
            )

    def update_task_status(
        self, status: str, requires_human_approval: bool = False, approved: bool | None = None
    ) -> None:
        with _connect() as conn:
            conn.execute(
                "UPDATE tasks SET status = ?, requires_human_approval = ?, approved = ?, updated_at = ? "
                "WHERE id = ?",
                (status, int(requires_human_approval), approved, time.time(), self.task_id),
            )

    def task_summary(self) -> dict:
        with _connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM traces WHERE task_id = ? ORDER BY created_at", (self.task_id,)
            ).fetchall()
            total_cost = sum(r["cost_usd"] for r in rows)
            total_latency = sum(r["latency_ms"] for r in rows)
            return {
                "task_id": self.task_id,
                "steps": [dict(r) for r in rows],
                "total_cost_usd": round(total_cost, 6),
                "total_latency_ms": round(total_latency, 1),
                "all_passed": all(r["passed"] for r in rows) if rows else True,
            }


def dashboard_query(limit: int = 200) -> list[dict]:
    """Used by the Streamlit dashboard to pull recent trace rows."""
    init_db()
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM traces ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def dashboard_tasks(limit: int = 100) -> list[dict]:
    init_db()
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def aggregate_metrics() -> dict:
    """
    System-wide metrics across every task ever processed — powers the
    /metrics endpoint. Mirrors the observability pattern used in the
    other projects (RepoMind AI's /metrics), adapted for a multi-agent
    graph: per-node latency/cost, task outcome breakdown, approval rate.
    """
    init_db()
    with _connect() as conn:
        conn.row_factory = sqlite3.Row

        total_tasks = conn.execute("SELECT COUNT(*) AS c FROM tasks").fetchone()["c"]

        status_rows = conn.execute(
            "SELECT status, COUNT(*) AS c FROM tasks GROUP BY status"
        ).fetchall()
        status_breakdown = {r["status"]: r["c"] for r in status_rows}

        approval_rows = conn.execute(
            "SELECT requires_human_approval, COUNT(*) AS c FROM tasks GROUP BY requires_human_approval"
        ).fetchall()
        approval_breakdown = {
            ("required" if r["requires_human_approval"] else "auto"): r["c"] for r in approval_rows
        }

        totals = conn.execute(
            "SELECT COUNT(*) AS steps, SUM(cost_usd) AS cost, "
            "SUM(input_tokens) AS in_tok, SUM(output_tokens) AS out_tok, "
            "AVG(latency_ms) AS avg_latency, "
            "SUM(CASE WHEN passed = 0 THEN 1 ELSE 0 END) AS failed_steps "
            "FROM traces"
        ).fetchone()

        node_rows = conn.execute(
            "SELECT node, COUNT(*) AS calls, AVG(latency_ms) AS avg_latency_ms, "
            "SUM(cost_usd) AS total_cost_usd, "
            "SUM(CASE WHEN passed = 0 THEN 1 ELSE 0 END) AS failures "
            "FROM traces GROUP BY node"
        ).fetchall()
        per_node = {
            r["node"]: {
                "calls": r["calls"],
                "avg_latency_ms": round(r["avg_latency_ms"] or 0.0, 2),
                "total_cost_usd": round(r["total_cost_usd"] or 0.0, 6),
                "failures": r["failures"],
            }
            for r in node_rows
        }

        completed = status_breakdown.get("done", 0) + status_breakdown.get("failed", 0)
        success_rate_pct = (
            round(status_breakdown.get("done", 0) / completed * 100, 1) if completed else None
        )

        return {
            "total_tasks": total_tasks,
            "status_breakdown": status_breakdown,
            "approval_breakdown": approval_breakdown,
            "success_rate_pct": success_rate_pct,
            "total_agent_steps": totals["steps"] or 0,
            "total_cost_usd": round(totals["cost"] or 0.0, 6),
            "total_input_tokens": totals["in_tok"] or 0,
            "total_output_tokens": totals["out_tok"] or 0,
            "avg_step_latency_ms": round(totals["avg_latency"] or 0.0, 2),
            "failed_steps": totals["failed_steps"] or 0,
            "per_node": per_node,
        }
