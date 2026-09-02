"""Tests for NoneBot-style console formatting and event mapping."""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.logger import (  # noqa: E402
    SUCCESS_LEVEL,
    _NoneBotStyleFormatter,
    _build_console_handler,
    _level_for_event,
    _logger_name_for_event,
    _message_for_event,
    console_log,
)
from study_qb_assistant.logger.console import (  # noqa: E402
    clear_console_logs,
    get_console_logs,
)
from study_qb_assistant.logger.storage import (  # noqa: E402
    cleanup_log_storage,
    configure_log_storage_policy,
    get_log_storage_stats,
    maybe_enforce_log_storage_policy,
)


class LoggerTests(unittest.TestCase):
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

    def test_console_log_buffer_records_and_clears(self) -> None:
        clear_console_logs()
        console_log("INFO", "测试控制台日志流记录")
        logs = get_console_logs(limit=10)
        self.assertTrue(any("测试控制台日志流记录" in item["message"] for item in logs))
        clear_console_logs()
        self.assertEqual(len(get_console_logs()), 0)

    def test_log_storage_stats_and_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "service.jsonl"
            log_file.write_text('{"event":"test"}\n', encoding="utf-8")
            old_file = Path(tmp_dir) / "service.old.jsonl"
            old_file.write_text('{"event":"old"}\n', encoding="utf-8")

            with mock.patch("study_qb_assistant.logger.storage.log_path", return_value=log_file):
                stats = get_log_storage_stats()
                self.assertEqual(stats["file_count"], 2)
                self.assertTrue(stats["total_size_bytes"] > 0)

                cleanup_res = cleanup_log_storage(keep_last_n_files=1)
                self.assertEqual(cleanup_res["deleted_files"], 1)
                after_stats = get_log_storage_stats()
                self.assertEqual(after_stats["file_count"], 1)

    def test_console_buffer_redacts_secret_values(self) -> None:
        clear_console_logs()
        console_log("WARNING", "Bearer sk_test-secret token: reset-secret")
        logs = get_console_logs(limit=10)
        self.assertTrue(logs)
        self.assertNotIn("sk_test-secret", logs[-1]["message"])
        self.assertNotIn("reset-secret", logs[-1]["message"])

    def test_log_storage_policy_removes_expired_archive_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "service.jsonl"
            log_file.write_text('{"event":"current"}\n', encoding="utf-8")
            old_file = Path(tmp_dir) / "service.old.jsonl"
            old_file.write_text('{"event":"old"}\n', encoding="utf-8")
            old_timestamp = time.time() - 2 * 86400
            os.utime(old_file, (old_timestamp, old_timestamp))

            configure_log_storage_policy(lambda: (1, 10))
            try:
                with mock.patch("study_qb_assistant.logger.storage.log_path", return_value=log_file):
                    maybe_enforce_log_storage_policy(force=True)
            finally:
                configure_log_storage_policy(None)

            self.assertFalse(old_file.exists())

if __name__ == "__main__":
    unittest.main()
