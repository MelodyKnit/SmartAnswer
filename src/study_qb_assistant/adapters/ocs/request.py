"""OCS 请求到内部题目查询的适配入口。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from study_qb_assistant.questions.models import QuestionQuery
from study_qb_assistant.questions.parsing import build_query_from_payload, split_options, split_raw_values


def parse_ocs_request(payload: Mapping[str, Any]) -> QuestionQuery:
    """解析 OCS GET/POST 载荷，并保留平台原始题型。"""

    normalized = dict(payload)
    if isinstance(normalized.get("options"), str):
        normalized["options"] = split_options(str(normalized["options"]))
    for field_name in ("image_urls", "image_data_urls"):
        if isinstance(normalized.get(field_name), str):
            normalized[field_name] = split_raw_values(str(normalized[field_name]))
    return build_query_from_payload(normalized)
