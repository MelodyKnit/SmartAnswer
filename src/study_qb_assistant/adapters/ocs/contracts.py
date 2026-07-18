"""OCS 集成对 API 层暴露的稳定契约。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from study_qb_assistant.questions.models import QueryResult, QuestionQuery


@runtime_checkable
class OcsIntegrationPort(Protocol):
    """OCS 请求解析、响应适配和资源渲染端口。"""

    def parse_request(self, payload: Mapping[str, Any]) -> QuestionQuery:
        """把 OCS 载荷解析为内部查询。"""

    def format_response(self, result: QueryResult) -> dict[str, object]:
        """把内部查询结果转换为 OCS 响应。"""

    def format_low_confidence_response(
        self,
        result: QueryResult,
        *,
        threshold: float,
    ) -> dict[str, object]:
        """生成低置信度拒答响应。"""

    def build_config(self, base_url: str, *, platform_name: str) -> list[dict[str, Any]]:
        """生成可导入 OCS 的题库配置。"""

    def render_client_script(self, base_url: str, *, token: str = "{{TOKEN}}") -> str:
        """渲染 OCS 客户端桥接脚本。"""
