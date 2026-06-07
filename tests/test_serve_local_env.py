"""Tests for local service startup environment loading."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import study_qb_assistant.runtime as runtime_module  # noqa: E402
from study_qb_assistant.runtime import load_local_env  # noqa: E402


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


def _restore_env(key: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
