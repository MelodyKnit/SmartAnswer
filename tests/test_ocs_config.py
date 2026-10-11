"""OCS 样式配置生成的单元测试。

本模块主要测试 `build_ocs_config` 能否根据提供的 Base URL 生成符合 OCS API 标准接口的配置 JSON，
并校验本地保存的静态配置文件（configs/ocs-local-study-bank.json）是否与默认生成的配置相匹配。
"""

from __future__ import annotations

import sys
import json
import shutil
import subprocess
import unittest
from pathlib import Path

# 将项目源文件目录 src 添加到 Python 路径中，以便能够正确导入项目模块。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.adapters import build_ocs_config  # noqa: E402
from study_qb_assistant.adapters.ocs.config import build_ocs_config_name  # noqa: E402
from study_qb_assistant.adapters.ocs.request import parse_ocs_request  # noqa: E402
from study_qb_assistant.api.contracts.query import QueryPayload  # noqa: E402


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
        self.assertEqual(item["v"], 2)
        self.assertEqual(item["method"], "post")
        self.assertEqual(item["type"], "GM_xmlhttpRequest")
        self.assertEqual(item["headers"]["Content-Type"], "application/json")
        self.assertIn("suggestion_title", item["data"]["title"]["handler"])
        self.assertIn("suggestion_options", item["data"]["options"]["handler"])
        self.assertIn("images", item["data"]["image_data_urls"]["handler"])
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

    @unittest.skipUnless(shutil.which("node"), "OCS JavaScript field handlers require Node.js")
    def test_field_handlers_execute_for_text_stem_and_option_images(self) -> None:
        """执行配置中的真实 JavaScript，再用 API 模型解析 OCS 构造的 JSON 请求。"""

        cases = [
            {"title": "文本题", "options": "A. 正确\nB. 错误", "type": "single"},
            {
                "title": "原图题干",
                "suggestion_title": "[图片1]",
                "options": "A. 正确\nB. 错误",
                "type": "single",
                "images": ["data:image/png;base64,AA=="],
            },
            {
                "title": "选项图片题",
                "suggestion_title": "选项图片题",
                "options": "原图选项",
                "suggestion_options": "A. [图片1]\nB. [图片2]",
                "type": "single",
                "images": ["data:image/png;base64,AA==", "data:image/png;base64,AQ=="],
            },
            {
                "title": "填空题",
                "options": "",
                "type": "completion",
                "images": [],
            },
        ]
        config = build_ocs_config("https://study.example.test", platform_name="AI题库")[0]
        # 与 OCS 字段处理协议相同：处理器先构造函数，再以 env 调用；图片数组保持数组类型。
        script = """
const {config, cases} = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const payloads = cases.map(env => Object.fromEntries(Object.entries(config.data).map(([key, value]) => [
  key, typeof value === 'object' && value.handler
    ? Function(value.handler)()(env)
    : value.replace(/\\$\\{(.*?)\\}/g, (_, name) => env[name] ?? '')
])));
process.stdout.write(JSON.stringify(payloads));
"""
        completed = subprocess.run(
            [shutil.which("node"), "-e", script],
            input=json.dumps({"config": config, "cases": cases}),
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
            timeout=10,
        )
        payloads = json.loads(completed.stdout)
        for env, payload in zip(cases, payloads, strict=True):
            with self.subTest(title=env["title"]):
                self.assertEqual(payload["title"], env.get("suggestion_title") or env["title"])
                self.assertEqual(
                    payload["options"], env.get("suggestion_options") or env["options"]
                )
                self.assertEqual(payload["image_data_urls"], env.get("images", []))
                query = parse_ocs_request(QueryPayload(**payload).model_dump())
                self.assertEqual(query.title, payload["title"])
                self.assertEqual(query.image_data_urls, tuple(payload["image_data_urls"]))

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
