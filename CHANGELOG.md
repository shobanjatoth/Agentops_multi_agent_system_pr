# Changelog

All notable changes to this project are documented here.

## [1.3.0] — Production Hardening & Deployment

### Added
- LLM response caching with a safe Redis/in-memory fallback and dashboard visibility for live operations.
- Hugging Face Spaces Docker configuration that keeps the FastAPI API private and serves the Streamlit dashboard publicly.

### Fixed
- Strict task, repository, concurrency, and batch-size validation at the API boundary.
- Approval now records authorization without executing an external action, preserving human-in-the-loop control.
- Network tool calls use bounded timeouts and local Docker services are not exposed unnecessarily.
- Ignore rules cover temporary pytest artifacts, lint caches, and accidental shell-output files.

## [1.2.0] — LLM Security Hardening

### Added
- `app/security.py`: pattern-based prompt-injection detection and `<untrusted_external_data>`
  fencing for content retrieved from external tools.
- Secret/credential leak scanning (`scan_for_secrets`) integrated into the Critic Agent —
  blocks any outbound action body resembling an API key, bearer token, or private key.
- 10 new tests covering both defenses, including a full `research_node` run against a
  simulated malicious GitHub issue body.
- `SECURITY.md` documenting the project's security scope and known limitations.

### Fixed
- Test-isolation bug: three `test_cache.py` tests expecting pure in-memory behaviour were
  inadvertently picking up the CI-level `REDIS_URL` environment variable (set so the
  separate real-Redis integration tests could run). Fixed with `monkeypatch.delenv` in the
  three affected tests.

## [1.1.0] — Reliability & Observability

### Added
- Redis-backed `ApprovalStore` with automatic in-memory fallback — pending approvals now
  survive process restarts and are shared across worker processes.
- `/tasks/batch` endpoint — semaphore-bounded concurrent processing of multiple tickets.
- `/metrics` endpoint — system-wide aggregate stats (success rate, per-node cost/latency).
- Optional LangSmith tracing via `@traceable` on LLM and tool calls.
- `benchmark.py` — reproducible benchmark script with 11 scenarios and self-validating
  expectation assertions.
- CI/CD: Redis service container in GitHub Actions, tag-triggered Docker Hub publish.

### Fixed
- Critic/approval action-type mismatch (`delete_resource` rejected as "unknown").
- Retry-exhausted tasks left at `in_progress` instead of `failed` — added explicit
  `mark_failed` terminal graph node.
- Two benchmark scenarios had incorrectly hand-calculated risk-score expectations,
  caught only once the benchmark's self-validation assertion was added.

## [1.0.0] — Initial Release

### Added
- Core LangGraph supervisor pattern: Triage, Research, Action, and Critic agents.
- Deterministic risk scoring and human-approval gate for high-risk actions.
- MCP-style tool layer (GitHub, Slack) with mock-mode fallback.
- FastAPI backend with SSE streaming for live task progress.
- Streamlit observability dashboard.
- SQLite-backed eval tracker (per-node latency, cost, pass/fail).
- Groq (free-tier) LLM integration.
- Initial test suite and GitHub Actions CI.
