# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in AgentOps, please report it privately
rather than opening a public issue.

- Email: satyam.ai.dev@gmail.com
- Please include: a description of the vulnerability, steps to reproduce, and the
  potential impact.
- You should receive an acknowledgment within 3–5 days.

## Scope

This project implements two categories of LLM-specific security controls, covered
by `app/security.py` and documented in the README under "LLM Security":

1. **Indirect prompt injection defense** — content retrieved from external, untrusted
   sources (GitHub issue bodies) is pattern-scanned and explicitly fenced before being
   included in any LLM prompt.
2. **Secret/credential leak scanning** — every outbound action body is scanned for
   patterns resembling API keys, bearer tokens, or private key material before it is
   allowed to pass the Critic Agent.

Both are deterministic, offline pattern-matching layers — they reduce risk but are
**not a complete guarantee** against a sufficiently novel injection technique. If you
find a way to bypass either defense, that is exactly the kind of report this policy
is for.

## Known Limitations

- `detect_prompt_injection()` and `scan_for_secrets()` are regex/pattern-based and
  will not catch every possible phrasing of an attack. They are the first layer of
  defense (detection + fencing), not the only one — the structural fencing in
  `wrap_untrusted()` is the primary defense, since it protects against injection
  attempts the pattern list doesn't recognize too.
- The human-approval gate (`app/approval.py`) is the final backstop for any
  high-risk action, regardless of whether the input-level defenses caught anything.
- API keys and tokens used by this project (`GROQ_API_KEY`, `GITHUB_TOKEN`,
  `SLACK_WEBHOOK_URL`, `LANGCHAIN_API_KEY`) should never be committed to the
  repository. `.gitignore` and `.dockerignore` both exclude `.env`.

## Supported Versions

This is an actively developed personal/portfolio project. Only the `main` branch
receives fixes; there are no maintained release branches.
