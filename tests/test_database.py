"""SQLite 连接并发 PRAGMA 的持久化行为测试。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.storage.database import get_engine  # noqa: E402


class SqliteConcurrencyPragmaTests(unittest.TestCase):
    def test_wal_is_enabled_and_connection_pragmas_apply_with_null_pool(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            engine = get_engine(Path(directory) / "runtime.sqlite3")
            for _ in range(2):
                with engine.connect() as connection:
                    journal_mode = connection.exec_driver_sql(
                        "PRAGMA journal_mode"
                    ).scalar_one()
                    busy_timeout = connection.exec_driver_sql(
                        "PRAGMA busy_timeout"
                    ).scalar_one()
                    synchronous = connection.exec_driver_sql(
                        "PRAGMA synchronous"
                    ).scalar_one()

                self.assertEqual(str(journal_mode).lower(), "wal")
                self.assertEqual(int(busy_timeout), 30000)
                self.assertEqual(int(synchronous), 1)


if __name__ == "__main__":
    unittest.main()
