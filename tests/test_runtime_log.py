"""Tests for NoneBot-style console formatting and event mapping."""

from __future__ import annotations

import logging
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.runtime_log import (  # noqa: E402
    SUCCESS_LEVEL,
    _NoneBotStyleFormatter,
    _build_console_handler,
    _level_for_event,
    _logger_name_for_event,
    _message_for_event,
)


class RuntimeLogTests(unittest.TestCase):
    def test_nonebot_style_formatter_matches_expected_shape(self) -> None:
        formatter = _NoneBotStyleFormatter(use_color=False)
        record = logging.LogRecord(
            name="study_qb_assistant.api",
            level=SUCCESS_LEVEL,
            pathname=__file__,
            lineno=1,
            msg="GET /ocs/query completion answer=南方谈话",
            args=(),
            exc_info=None,
        )

        rendered = formatter.format(record)

        self.assertIn("[SUCCESS]", rendered)
        self.assertIn("study_qb_assistant.api", rendered)
        self.assertIn("| GET /ocs/query completion answer=南方谈话", rendered)

    def test_event_level_mapping_marks_query_success_as_success(self) -> None:
        level = _level_for_event("query", {"ok": True})
        self.assertEqual(level, SUCCESS_LEVEL)

    def test_event_level_mapping_marks_search_errors_as_warning(self) -> None:
        level = _level_for_event("web_search_error", {})
        self.assertEqual(level, logging.WARNING)

    def test_logger_name_mapping_uses_subsystem_names(self) -> None:
        self.assertEqual(_logger_name_for_event("model_request"), "study_qb_assistant.model")
        self.assertEqual(_logger_name_for_event("web_search_results"), "study_qb_assistant.search")
        self.assertEqual(_logger_name_for_event("query"), "study_qb_assistant.api")

    def test_query_message_contains_nonebot_style_summary_fields(self) -> None:
        message = _message_for_event(
            "query",
            {
                "method": "GET",
                "path": "/ocs/query",
                "question_type": "completion",
                "answer": "共同富裕",
                "confidence": 0.99,
                "resolution_mode": "llm_fallback",
                "title": "填空题(1分)社会主义本质是解放生产力、发展生产力，消灭剥削，消除两极分化，最终达到【1】____。",
            },
        )

        self.assertIn("GET /ocs/query", message)
        self.assertIn("completion", message)
        self.assertIn("共同富裕", message)

    def test_console_handler_uses_nonebot_formatter(self) -> None:
        handler = _build_console_handler()
        self.assertIsInstance(handler.formatter, _NoneBotStyleFormatter)


if __name__ == "__main__":
    unittest.main()
