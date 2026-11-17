"""
Minimal MCP-style tool interface.

Real MCP servers expose tools over a JSON-RPC-ish protocol; here we keep
the same *shape* (name, input schema, `call()` returning structured
output) so swapping these for a real `langchain-mcp-adapters` client
later is a drop-in change, not a rewrite. Each tool degrades to a
deterministic mock when no credentials are configured, so the whole
project runs and is testable with zero external accounts.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from langsmith import traceable


@dataclass
class ToolResult:
    output: dict
    latency_ms: float
    mocked: bool


class MCPTool(ABC):
    name: str

    @abstractmethod
    def _run(self, **kwargs) -> dict: ...

    def call(self, **kwargs) -> ToolResult:
        return self._traced_call(**kwargs)

    @traceable(name="mcp_tool_call", run_type="tool")
    def _traced_call(self, **kwargs) -> ToolResult:
        start = time.perf_counter()
        output = self._run(**kwargs)
        latency_ms = (time.perf_counter() - start) * 1000
        return ToolResult(output=output, latency_ms=latency_ms, mocked=getattr(self, "is_mocked", False))


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, MCPTool] = {}

    def register(self, tool: MCPTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> MCPTool:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' is not registered")
        return self._tools[name]

    def names(self) -> list[str]:
        return list(self._tools.keys())
