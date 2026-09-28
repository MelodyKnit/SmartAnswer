"""系统查题保护配置校验测试。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.auth import AuthError  # noqa: E402
from study_qb_assistant.platform.container import PlatformServices  # noqa: E402


class QueryProtectionConfigTests(unittest.TestCase):
    def test_query_protection_settings_accept_bounds_and_reject_out_of_range(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = PlatformServices(Path(directory) / "runtime.sqlite3").settings
            saved = settings.set_system_config(
                {
                    "query_rate_limit_enabled": "false",
                    "query_rate_limit_window_seconds": "3600",
                    "query_rate_limit_requests_per_user": "600",
                    "query_max_active_requests_per_user": "8",
                    "query_max_active_requests": "32",
                }
            )

            self.assertEqual(saved["query_rate_limit_enabled"], "false")
            self.assertEqual(saved["query_max_active_requests"], "32")
            for key, invalid in (
                ("query_rate_limit_window_seconds", "9"),
                ("query_rate_limit_requests_per_user", "601"),
                ("query_max_active_requests_per_user", "9"),
                ("query_max_active_requests", "33"),
            ):
                with self.subTest(key=key, invalid=invalid):
                    with self.assertRaises(AuthError):
                        settings.set_system_config({key: invalid})


if __name__ == "__main__":
    unittest.main()
