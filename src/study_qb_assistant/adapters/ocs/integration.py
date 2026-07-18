"""默认 OCS 集成 Facade。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from study_qb_assistant.questions.models import QueryResult, QuestionQuery
from .config import build_ocs_config, render_ocs_client_script
from .registry import OcsQuestionTypeRegistry
from .request import parse_ocs_request
from .response import to_ocs_low_confidence_response, to_ocs_response


class DefaultOcsIntegration:
    """封装 OCS 请求、响应、配置与脚本资源的默认实现。"""

    def __init__(self, registry: OcsQuestionTypeRegistry | None = None) -> None:
        self.registry = registry or OcsQuestionTypeRegistry.with_defaults()

    def parse_request(self, payload: Mapping[str, Any]) -> QuestionQuery:
        return parse_ocs_request(payload)

    def format_response(self, result: QueryResult) -> dict[str, object]:
        return to_ocs_response(result, registry=self.registry)

    def format_low_confidence_response(
        self,
        result: QueryResult,
        *,
        threshold: float,
    ) -> dict[str, object]:
        return to_ocs_low_confidence_response(result, threshold=threshold)

    def build_config(self, base_url: str, *, platform_name: str) -> list[dict[str, Any]]:
        return build_ocs_config(base_url, platform_name=platform_name)

    def render_client_script(self, base_url: str, *, token: str = "{{TOKEN}}") -> str:
        return render_ocs_client_script(base_url, token=token)
