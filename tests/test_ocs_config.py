"""OCS 样式配置生成的单元测试。

本模块主要测试 `build_ocs_config` 能否根据提供的 Base URL 生成符合 OCS API 标准接口的配置 JSON，
并校验本地保存的静态配置文件（configs/ocs-local-study-bank.json）是否与默认生成的配置相匹配。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# 将项目源文件目录 src 添加到 Python 路径中，以便能够正确导入项目模块
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.adapters import build_ocs_config  # noqa: E402


class OcsConfigTests(unittest.TestCase):
    """测试 OCS 配置生成逻辑的测试类。"""

    def test_config_uses_base_url_and_required_fields(self) -> None:
        """测试配置生成是否正确应用了 Base URL，且包含所有必需的原生 OCS 规范字段。
        
        校验生成的 homepage 监控探针、API 请求接口 url、请求类型（GM_xmlhttpRequest）、
        参数占位符（${title}）以及 OCS 标准回调处理器（handler）。
        """
        config = build_ocs_config("http://127.0.0.1:8765/")

        self.assertEqual(len(config), 1)
        item = config[0]
        # 验证 OCS 题库的在线状态监测 URL，默认为 Base URL 下的 healthz
        self.assertEqual(item["homepage"], "http://127.0.0.1:8765/healthz")
        # 验证 OCS 查询的 API 端点
        self.assertEqual(item["url"], "http://127.0.0.1:8765/ocs/query")
        self.assertEqual(item["type"], "GM_xmlhttpRequest")
        # OCS 变量占位符规范
        self.assertEqual(item["data"]["title"], "${title}")
        # OCS 回调 JS 代码规范段
        self.assertIn("[res.data.question, res.data.answer]", item["handler"])

    def test_static_config_matches_generated_default(self) -> None:
        """测试本地静态保存的 `ocs-local-study-bank.json` 是否与代码默认生成的配置完全一致。
        
        这可以避免后续修改了配置生成逻辑后，遗漏更新已分发的静态配置文件。
        """
        import json

        # 读取本地物理存储的静态配置
        static_config = json.loads(
            (PROJECT_ROOT / "configs" / "ocs-local-study-bank.json").read_text(encoding="utf-8")
        )

        # 断言静态配置应与默认 Base URL 生成出来的结果完全一致
        self.assertEqual(static_config, build_ocs_config("http://127.0.0.1:8765"))


if __name__ == "__main__":
    unittest.main()
