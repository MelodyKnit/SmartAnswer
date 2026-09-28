"""模型实例配置唯一来源与旧数据库迁移测试。"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.bootstrap import build_base_model_provider  # noqa: E402
from study_qb_assistant.platform.container import PlatformServices  # noqa: E402


class LlmConfigSourceTests(unittest.TestCase):
    def test_environment_model_parameters_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            platform = PlatformServices(Path(directory) / "runtime.sqlite3")
            with patch.dict(
                os.environ,
                {
                    "STQB_LLM_BASE_URL": "https://env-only.example/v1",
                    "STQB_LLM_MODEL": "env-only-model",
                    "STQB_LLM_API_KEY": "env-only-secret",
                },
            ):
                provider = build_base_model_provider(platform.llm)

        self.assertIsNone(provider)

    def test_legacy_database_model_settings_migrate_to_model_table(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            platform = PlatformServices(Path(directory) / "runtime.sqlite3")
            platform.settings.repository.set_settings(
                "system_config",
                {
                    "llm_base_url": "https://legacy-db.example/v1",
                    "llm_model": "legacy-db-model",
                    "llm_api_key": "legacy-db-secret",
                },
            )

            platform.settings.get_llm_runtime_config()
            models = platform.llm.active_models()

        self.assertEqual(len(models), 1)
        self.assertEqual(models[0].base_url, "https://legacy-db.example/v1")
        self.assertEqual(models[0].model, "legacy-db-model")
        self.assertEqual(models[0].api_key, "legacy-db-secret")


if __name__ == "__main__":
    unittest.main()
