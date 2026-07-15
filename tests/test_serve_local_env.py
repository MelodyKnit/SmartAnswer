"""Tests for local service startup environment loading."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import study_qb_assistant.bootstrap as runtime_module  # noqa: E402
import study_qb_assistant.config as config_module  # noqa: E402
from study_qb_assistant.bootstrap import load_local_env  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


class ServeLocalEnvTests(unittest.TestCase):
    """Ensure `.env` / `.env.local` loading remains non-destructive and dotenv-compatible."""

    def test_load_local_env_uses_file_without_overriding_existing_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env.local"
            env_path.write_text(
                "STQB_TEST_EXISTING=file-value\nSTQB_TEST_NEW='new value'\n",
                encoding="utf-8",
            )
            previous_existing = os.environ.get("STQB_TEST_EXISTING")
            previous_new = os.environ.get("STQB_TEST_NEW")
            os.environ["STQB_TEST_EXISTING"] = "process-value"
            os.environ.pop("STQB_TEST_NEW", None)
            try:
                load_local_env(env_path)

                self.assertEqual(os.environ["STQB_TEST_EXISTING"], "process-value")
                self.assertEqual(os.environ["STQB_TEST_NEW"], "new value")
            finally:
                _restore_env("STQB_TEST_EXISTING", previous_existing)
                _restore_env("STQB_TEST_NEW", previous_new)

    def test_load_local_env_reads_both_project_files_when_project_root_is_patched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dot_env = root / ".env"
            dot_env_local = root / ".env.local"
            dot_env.write_text(
                "STQB_TEST_FROM_ENV=base-value\nSTQB_TEST_SHARED=from-env\n",
                encoding="utf-8",
            )
            dot_env_local.write_text(
                "STQB_TEST_FROM_LOCAL=local-value\nSTQB_TEST_SHARED=from-local\n",
                encoding="utf-8",
            )
            previous_root = runtime_module.PROJECT_ROOT
            previous_base = os.environ.get("STQB_TEST_FROM_ENV")
            previous_local = os.environ.get("STQB_TEST_FROM_LOCAL")
            previous_shared = os.environ.get("STQB_TEST_SHARED")
            os.environ.pop("STQB_TEST_FROM_ENV", None)
            os.environ.pop("STQB_TEST_FROM_LOCAL", None)
            os.environ.pop("STQB_TEST_SHARED", None)
            try:
                runtime_module.PROJECT_ROOT = root
                load_local_env()
                self.assertEqual(os.environ["STQB_TEST_FROM_ENV"], "base-value")
                self.assertEqual(os.environ["STQB_TEST_FROM_LOCAL"], "local-value")
                # `.env` is loaded first and existing env vars are preserved, so `.env.local`
                # must not overwrite the shared key.
                self.assertEqual(os.environ["STQB_TEST_SHARED"], "from-env")
            finally:
                runtime_module.PROJECT_ROOT = previous_root
                _restore_env("STQB_TEST_FROM_ENV", previous_base)
                _restore_env("STQB_TEST_FROM_LOCAL", previous_local)
                _restore_env("STQB_TEST_SHARED", previous_shared)

    def test_build_runtime_app_starts_with_missing_question_bank_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir = root / "data"
            normalized_dir = data_dir / "normalized"
            runtime_dir = data_dir / "runtime"
            logs_dir = data_dir / "logs"
            database_path = Path(directory) / "runtime" / "study-qb.sqlite3"
            log_path = Path(directory) / "logs" / "service.jsonl"
            missing_index = Path(directory) / "normalized" / "verified.jsonl"
            previous_values = {
                "STQB_DATABASE_PATH": os.environ.get("STQB_DATABASE_PATH"),
                "STQB_LOG_PATH": os.environ.get("STQB_LOG_PATH"),
                "STQB_INDEX_PATH": os.environ.get("STQB_INDEX_PATH"),
                "STQB_REQUIRE_AUTH": os.environ.get("STQB_REQUIRE_AUTH"),
            }
            os.environ["STQB_DATABASE_PATH"] = str(database_path)
            os.environ["STQB_LOG_PATH"] = str(log_path)
            os.environ["STQB_INDEX_PATH"] = str(missing_index)
            os.environ["STQB_REQUIRE_AUTH"] = "false"
            try:
                with (
                    patch.object(runtime_module, "PROJECT_ROOT", root),
                    patch.object(config_module, "PROJECT_ROOT", root),
                    patch.object(config_module, "SRC_ROOT", root / "src"),
                    patch.object(config_module, "CONFIG_DIR", root / "configs"),
                    patch.object(config_module, "DATA_DIR", data_dir),
                    patch.object(config_module, "DATA_RAW_DIR", data_dir / "raw"),
                    patch.object(config_module, "DATA_NORMALIZED_DIR", normalized_dir),
                    patch.object(config_module, "DATA_RUNTIME_DIR", runtime_dir),
                    patch.object(config_module, "DATA_LOGS_DIR", logs_dir),
                ):
                    app = runtime_module.build_runtime_app()
                    client = TestClient(app)

                    health = client.get("/healthz")
                    status = client.get("/status")
                    query = client.get(
                        "/query",
                        params={"title": "尚未导入的题目", "type": "single"},
                    )

                    self.assertEqual(health.status_code, 200)
                    self.assertTrue(health.json()["ok"])
                    self.assertEqual(status.status_code, 200)
                    self.assertEqual(status.json()["lookup"]["record_count"], 0)
                    self.assertEqual(query.status_code, 200)
                    self.assertFalse(query.json()["ok"])
                    self.assertEqual(query.json()["error"]["code"], "NOT_FOUND")
            finally:
                for key, value in previous_values.items():
                    _restore_env(key, value)

    def test_data_dir_controls_default_runtime_paths(self) -> None:
        """默认运行数据应由 STQB_DATA_DIR 统一控制，便于容器空数据部署。"""
        with tempfile.TemporaryDirectory() as directory:
            previous_values = {
                "STQB_DATA_DIR": os.environ.get("STQB_DATA_DIR"),
                "STQB_DATABASE_PATH": os.environ.get("STQB_DATABASE_PATH"),
                "STQB_LOG_PATH": os.environ.get("STQB_LOG_PATH"),
                "STQB_INDEX_PATH": os.environ.get("STQB_INDEX_PATH"),
            }
            os.environ["STQB_DATA_DIR"] = str(Path(directory) / "deploy-data")
            os.environ.pop("STQB_DATABASE_PATH", None)
            os.environ.pop("STQB_LOG_PATH", None)
            os.environ.pop("STQB_INDEX_PATH", None)
            try:
                config = config_module.get_global_config()
                self.assertEqual(
                    config.database_path_resolved,
                    Path(directory) / "deploy-data" / "runtime" / "study-qb.sqlite3",
                )
                self.assertEqual(
                    config.log_path_resolved,
                    Path(directory) / "deploy-data" / "logs" / "service.jsonl",
                )
                self.assertEqual(
                    config.index_path_resolved,
                    Path(directory) / "deploy-data" / "normalized" / "verified.jsonl",
                )
            finally:
                for key, value in previous_values.items():
                    _restore_env(key, value)


def _restore_env(key: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
