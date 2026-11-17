

# from __future__ import annotations

# import os

# import httpx

# from app.tools.base import MCPTool


# class SlackTool(MCPTool):
#     name = "slack"

#     def __init__(self):
#         self.webhook_url = os.getenv("SLACK_WEBHOOK_URL")
#         self.is_mocked = self.webhook_url is None

#     def _run(self, action: str, **kwargs) -> dict:
#         if action != "notify":
#             raise ValueError(f"Unknown Slack action: {action}")
#         return self._notify(**kwargs)

#     def _notify(self, message: str, channel: str = "#agentops") -> dict:
#         if self.is_mocked:
#             return {"mocked": True, "sent": True, "channel": channel, "message": message}
#         resp = httpx.post(self.webhook_url, json={"text": f"[{channel}] {message}"}, timeout=15.0)
#         resp.raise_for_status()
#         return {"mocked": False, "sent": True, "status_code": resp.status_code}










from __future__ import annotations

import os

import httpx

from app.tools.base import MCPTool


class SlackTool(MCPTool):
    name = "slack"

    def __init__(self, mocked: bool | None = None):
        self.webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        self.is_mocked = (
            self.webhook_url is None if mocked is None else mocked
        )

    def _run(self, action: str, **kwargs) -> dict:
        if action != "notify":
            raise ValueError(f"Unknown Slack action: {action}")

        return self._notify(**kwargs)

    def _notify(
        self,
        message: str,
        channel: str = "#agentops",
    ) -> dict:
        if not message.strip():
            raise ValueError("Slack message cannot be empty")

        if self.is_mocked:
            return {
                "mocked": True,
                "sent": True,
                "channel": channel,
                "message": message,
            }

        if not self.webhook_url:
            raise ValueError("SLACK_WEBHOOK_URL is not configured")

        resp = httpx.post(
            self.webhook_url,
            json={"text": f"[{channel}] {message}"},
            timeout=15.0,
        )
        resp.raise_for_status()

        return {
            "mocked": False,
            "sent": True,
            "status_code": resp.status_code,
        }
