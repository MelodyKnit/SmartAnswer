"""LLM 工具注册表。"""

from __future__ import annotations

from collections.abc import Iterable

from .base import BaseLlmTool


class LlmToolRegistry:
    """按名称和能力管理 LLM 工具。"""

    def __init__(self, tools: Iterable[BaseLlmTool] = ()) -> None:
        self.tools: dict[str, BaseLlmTool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: BaseLlmTool) -> None:
        """注册工具，名称重复时拒绝覆盖。"""

        name = tool.tool_name.strip()
        if not name:
            raise ValueError("LLM 工具名称不能为空")
        if name in self.tools:
            raise ValueError(f"LLM 工具名称重复: {name}")
        self.tools[name] = tool

    def get(self, tool_name: str) -> BaseLlmTool:
        """按名称读取工具。"""

        try:
            return self.tools[tool_name]
        except KeyError as exc:
            raise KeyError(f"未注册 LLM 工具: {tool_name}") from exc

    def by_capability(self, capability: str) -> tuple[BaseLlmTool, ...]:
        """返回声明指定能力的全部工具。"""

        return tuple(tool for tool in self.tools.values() if capability in tool.capabilities)

    def statuses(self) -> tuple[dict[str, object], ...]:
        """返回所有工具的状态快照。"""

        return tuple(tool.status() for tool in self.tools.values())
