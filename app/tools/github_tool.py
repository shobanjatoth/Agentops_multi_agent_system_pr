# from __future__ import annotations

# import os
# import re

# import httpx

# from app.tools.base import MCPTool

# GITHUB_API = "https://api.github.com"
# _REPO_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


# class GitHubTool(MCPTool):
#     name = "github"

#     def __init__(self):
#         self.token = os.getenv("GITHUB_TOKEN")
#         self.is_mocked = self.token is None

#     def _headers(self) -> dict:
#         return {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json"}

#     def _run(self, action: str, repo: str, **kwargs) -> dict:
#         if not _REPO_SLUG_RE.fullmatch(repo):
#             raise ValueError("repo must be a GitHub owner/repository slug")
#         handler = {
#             "list_issues": self._list_issues,
#             "get_issue": self._get_issue,
#             "post_comment": self._post_comment,
#             "open_pr": self._open_pr,
#         }.get(action)
#         if handler is None:
#             raise ValueError(f"Unknown GitHub action: {action}")
#         return handler(repo, **kwargs)

#     # ---- real / mocked handlers ----

#     def _list_issues(self, repo: str, state: str = "open") -> dict:
#         if self.is_mocked:
#             return {
#                 "mocked": True,
#                 "issues": [
#                     {"number": 101, "title": "Login fails on mobile Safari", "state": "open"},
#                     {"number": 98, "title": "Add dark mode toggle", "state": "open"},
#                 ],
#             }
#         resp = httpx.get(
#             f"{GITHUB_API}/repos/{repo}/issues", headers=self._headers(), params={"state": state}, timeout=15.0
#         )
#         resp.raise_for_status()
#         return {"mocked": False, "issues": resp.json()}

#     def _get_issue(self, repo: str, issue_number: int) -> dict:
#         if self.is_mocked:
#             return {
#                 "mocked": True,
#                 "issue": {
#                     "number": issue_number,
#                     "title": "Login fails on mobile Safari after last deploy",
#                     "body": "Multiple users report the login button does nothing on iOS Safari "
#                     "since the 2.4.1 release. Chrome/Firefox unaffected.",
#                 },
#             }
#         if issue_number < 1:
#             raise ValueError("issue_number must be positive")
#         resp = httpx.get(f"{GITHUB_API}/repos/{repo}/issues/{issue_number}", headers=self._headers(), timeout=15.0)
#         resp.raise_for_status()
#         return {"mocked": False, "issue": resp.json()}

#     def _post_comment(self, repo: str, issue_number: int, body: str) -> dict:
#         if self.is_mocked:
#             return {"mocked": True, "posted": True, "issue_number": issue_number, "body": body}
#         resp = httpx.post(
#             f"{GITHUB_API}/repos/{repo}/issues/{issue_number}/comments",
#             headers=self._headers(),
#             json={"body": body},
#             timeout=15.0,
#         )
#         resp.raise_for_status()
#         return {"mocked": False, "posted": True, "response": resp.json()}

#     def _open_pr(self, repo: str, title: str, body: str, head: str, base: str = "main") -> dict:
#         if self.is_mocked:
#             return {"mocked": True, "opened": True, "title": title, "head": head, "base": base}
#         resp = httpx.post(
#             f"{GITHUB_API}/repos/{repo}/pulls",
#             headers=self._headers(),
#             json={"title": title, "body": body, "head": head, "base": base},
#             timeout=15.0,
#         )
#         resp.raise_for_status()
#         return {"mocked": False, "opened": True, "response": resp.json()}














# from __future__ import annotations

# import os
# import re

# import httpx

# from app.tools.base import MCPTool

# GITHUB_API = "https://api.github.com"

# _REPO_SLUG_RE = re.compile(
#     r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
# )


# class GitHubTool(MCPTool):
#     name = "github"

#     def __init__(self):
#         self.token = (os.getenv("GITHUB_TOKEN") or "").strip()
#         self.is_mocked = not bool(self.token)

#     def _headers(self) -> dict:
#         headers = {
#             "Accept": "application/vnd.github+json",
#             "X-GitHub-Api-Version": "2022-11-28",
#         }

#         if self.token:
#             headers["Authorization"] = f"Bearer {self.token}"

#         return headers

#     def _run(self, action: str, repo: str, **kwargs) -> dict:
#         if not _REPO_SLUG_RE.fullmatch(repo):
#             raise ValueError(
#                 "repo must be a GitHub owner/repository slug"
#             )

#         handler = {
#             "list_issues": self._list_issues,
#             "get_issue": self._get_issue,
#             "post_comment": self._post_comment,
#             "open_pr": self._open_pr,
#         }.get(action)

#         if handler is None:
#             raise ValueError(f"Unknown GitHub action: {action}")

#         return handler(repo, **kwargs)

#     # -------------------------
#     # List GitHub issues
#     # -------------------------

#     def _list_issues(
#         self,
#         repo: str,
#         state: str = "open"
#     ) -> dict:

#         if self.is_mocked:
#             return {
#                 "mocked": True,
#                 "issues": [
#                     {
#                         "number": 101,
#                         "title": "Login fails on mobile Safari",
#                         "state": "open",
#                     },
#                     {
#                         "number": 98,
#                         "title": "Add dark mode toggle",
#                         "state": "open",
#                     },
#                 ],
#             }

#         if state not in {"open", "closed", "all"}:
#             raise ValueError("state must be open, closed, or all")

#         resp = httpx.get(
#             f"{GITHUB_API}/repos/{repo}/issues",
#             headers=self._headers(),
#             params={"state": state},
#             timeout=15.0,
#         )

#         resp.raise_for_status()

#         return {
#             "mocked": False,
#             "issues": resp.json(),
#         }

#     # -------------------------
#     # Get a specific issue
#     # -------------------------

#     def _get_issue(
#         self,
#         repo: str,
#         issue_number: int
#     ) -> dict:

#         if issue_number < 1:
#             raise ValueError("issue_number must be positive")

#         if self.is_mocked:
#             return {
#                 "mocked": True,
#                 "issue": {
#                     "number": issue_number,
#                     "title": "Login fails on mobile Safari after last deploy",
#                     "body": (
#                         "Multiple users report the login button does "
#                         "nothing on iOS Safari since the 2.4.1 release. "
#                         "Chrome/Firefox unaffected."
#                     ),
#                 },
#             }

#         resp = httpx.get(
#             f"{GITHUB_API}/repos/{repo}/issues/{issue_number}",
#             headers=self._headers(),
#             timeout=15.0,
#         )

#         resp.raise_for_status()

#         return {
#             "mocked": False,
#             "issue": resp.json(),
#         }

#     # -------------------------
#     # Post a comment
#     # -------------------------

#     def _post_comment(
#         self,
#         repo: str,
#         issue_number: int,
#         body: str
#     ) -> dict:

#         if issue_number < 1:
#             raise ValueError("issue_number must be positive")

#         if not body.strip():
#             raise ValueError("Comment body cannot be empty")

#         if self.is_mocked:
#             return {
#                 "mocked": True,
#                 "posted": True,
#                 "issue_number": issue_number,
#                 "body": body,
#             }

#         resp = httpx.post(
#             f"{GITHUB_API}/repos/{repo}/issues/{issue_number}/comments",
#             headers=self._headers(),
#             json={"body": body},
#             timeout=15.0,
#         )

#         resp.raise_for_status()

#         return {
#             "mocked": False,
#             "posted": True,
#             "response": resp.json(),
#         }

#     # -------------------------
#     # Open a pull request
#     # -------------------------

#     def _open_pr(
#         self,
#         repo: str,
#         title: str,
#         body: str,
#         head: str,
#         base: str = "main"
#     ) -> dict:

#         if not title.strip():
#             raise ValueError("PR title cannot be empty")

#         if not head.strip():
#             raise ValueError("PR head branch cannot be empty")

#         if self.is_mocked:
#             return {
#                 "mocked": True,
#                 "opened": True,
#                 "title": title,
#                 "head": head,
#                 "base": base,
#             }

#         resp = httpx.post(
#             f"{GITHUB_API}/repos/{repo}/pulls",
#             headers=self._headers(),
#             json={
#                 "title": title,
#                 "body": body,
#                 "head": head,
#                 "base": base,
#             },
#             timeout=15.0,
#         )

#         resp.raise_for_status()

#         return {
#             "mocked": False,
#             "opened": True,
#             "response": resp.json(),
#         }
















from __future__ import annotations

import os
import re

import httpx

from app.tools.base import MCPTool

GITHUB_API = "https://api.github.com"

_REPO_SLUG_RE = re.compile(
    r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
)


class GitHubTool(MCPTool):
    name = "github"

    def __init__(self, mocked: bool | None = None):
        self.token = (os.getenv("GITHUB_TOKEN") or "").strip()
        self.is_mocked = (
            not bool(self.token) if mocked is None else mocked
        )

    def _headers(self) -> dict:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        return headers

    def _run(self, action: str, repo: str, **kwargs) -> dict:
        if not _REPO_SLUG_RE.fullmatch(repo):
            raise ValueError(
                "repo must be a GitHub owner/repository slug"
            )

        handler = {
            "list_issues": self._list_issues,
            "get_issue": self._get_issue,
            "post_comment": self._post_comment,
            "open_pr": self._open_pr,
        }.get(action)

        if handler is None:
            raise ValueError(f"Unknown GitHub action: {action}")

        return handler(repo, **kwargs)

    def _list_issues(
        self,
        repo: str,
        state: str = "open",
    ) -> dict:
        if state not in {"open", "closed", "all"}:
            raise ValueError("state must be open, closed, or all")

        if self.is_mocked:
            return {
                "mocked": True,
                "issues": [
                    {
                        "number": 101,
                        "title": "Login fails on mobile Safari",
                        "state": "open",
                    },
                    {
                        "number": 98,
                        "title": "Add dark mode toggle",
                        "state": "open",
                    },
                ],
            }

        resp = httpx.get(
            f"{GITHUB_API}/repos/{repo}/issues",
            headers=self._headers(),
            params={"state": state},
            timeout=15.0,
        )
        resp.raise_for_status()

        return {
            "mocked": False,
            "issues": resp.json(),
        }

    def _get_issue(
        self,
        repo: str,
        issue_number: int,
    ) -> dict:
        if issue_number < 1:
            raise ValueError("issue_number must be positive")

        if self.is_mocked:
            return {
                "mocked": True,
                "issue": {
                    "number": issue_number,
                    "title": "Login fails on mobile Safari after last deploy",
                    "body": (
                        "Multiple users report the login button does "
                        "nothing on iOS Safari since the 2.4.1 release. "
                        "Chrome/Firefox unaffected."
                    ),
                },
            }

        resp = httpx.get(
            f"{GITHUB_API}/repos/{repo}/issues/{issue_number}",
            headers=self._headers(),
            timeout=15.0,
        )
        resp.raise_for_status()

        return {
            "mocked": False,
            "issue": resp.json(),
        }

    def _post_comment(
        self,
        repo: str,
        issue_number: int,
        body: str,
    ) -> dict:
        if issue_number < 1:
            raise ValueError("issue_number must be positive")

        if not body.strip():
            raise ValueError("Comment body cannot be empty")

        if self.is_mocked:
            return {
                "mocked": True,
                "posted": True,
                "issue_number": issue_number,
                "body": body,
            }

        resp = httpx.post(
            f"{GITHUB_API}/repos/{repo}/issues/{issue_number}/comments",
            headers=self._headers(),
            json={"body": body},
            timeout=15.0,
        )
        resp.raise_for_status()

        return {
            "mocked": False,
            "posted": True,
            "response": resp.json(),
        }

    def _open_pr(
        self,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str = "main",
    ) -> dict:
        if not title.strip():
            raise ValueError("PR title cannot be empty")

        if not body.strip():
            raise ValueError("PR body cannot be empty")

        if not head.strip():
            raise ValueError("PR head branch cannot be empty")

        if not base.strip():
            raise ValueError("PR base branch cannot be empty")

        if self.is_mocked:
            return {
                "mocked": True,
                "opened": True,
                "title": title,
                "head": head,
                "base": base,
            }

        resp = httpx.post(
            f"{GITHUB_API}/repos/{repo}/pulls",
            headers=self._headers(),
            json={
                "title": title,
                "body": body,
                "head": head,
                "base": base,
            },
            timeout=15.0,
        )
        resp.raise_for_status()

        return {
            "mocked": False,
            "opened": True,
            "response": resp.json(),
        }
