"""OCS 样式配置生成的单元测试。

本模块主要测试 `build_ocs_config` 能否根据提供的 Base URL 生成符合 OCS API 标准接口的配置 JSON，
并校验本地保存的静态配置文件（configs/ocs-local-study-bank.json）是否与默认生成的配置相匹配。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# 将项目源文件目录 src 添加到 Python 路径中，以便能够正确导入项目模块。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.adapters import build_ocs_config  # noqa: E402
from study_qb_assistant.adapters.ocs.config import build_ocs_config_name  # noqa: E402


class OcsConfigTests(unittest.TestCase):
    """测试 OCS 配置生成逻辑的测试类。"""

    def test_config_uses_base_url_and_required_fields(self) -> None:
        """测试配置生成是否正确应用 Base URL，并包含 OCS 必需字段。"""
        config = build_ocs_config("http://127.0.0.1:8765/", platform_name="AI题库")

        self.assertEqual(len(config), 1)
        item = config[0]
        self.assertEqual(item["name"], "AI题库")
        self.assertEqual(item["homepage"], "http://127.0.0.1:8765/api/v1/healthz")
        self.assertEqual(item["url"], "http://127.0.0.1:8765/ocs/query")
        self.assertEqual(item["type"], "GM_xmlhttpRequest")
        self.assertEqual(item["data"]["title"], "${title}")
        self.assertIn("[res.data.question, res.data.answer", item["handler"])
        self.assertNotIn("[res.data.answer, res.data.question", item["handler"])

    def test_static_config_matches_generated_default(self) -> None:
        """测试本地静态配置是否与默认 Base URL 生成结果一致。"""
        import json

        static_config = json.loads(
            (PROJECT_ROOT / "configs" / "ocs-local-study-bank.json").read_text(encoding="utf-8")
        )

        self.assertEqual(
            static_config,
            build_ocs_config("http://127.0.0.1:8765", platform_name="AI题库"),
        )

    def test_config_name_uses_platform_and_token_context(self) -> None:
        """有令牌上下文的配置使用平台标题与 API Key 名称。"""

        config = build_ocs_config(
            "http://127.0.0.1:8765",
            platform_name="学习服务",
            token_description="宿舍电脑",
            token_key_mask="sk_stqb_abc...wxyz",
        )

        self.assertEqual(config[0]["name"], "学习服务 · 宿舍电脑")
        self.assertEqual(
            build_ocs_config_name("学习服务", token_key_mask="sk_stqb_abc...wxyz"),
            "学习服务 · wxyz",
        )


if __name__ == "__main__":
    unittest.main()
