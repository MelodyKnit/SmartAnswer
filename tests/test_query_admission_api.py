"""查题准入保护的公开接口回归测试。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.api.app import create_app  # noqa: E402
from study_qb_assistant.answering import AnswerService  # noqa: E402
from study_qb_assistant.auth import AuthService  # noqa: E402
from study_qb_assistant.platform.container import PlatformServices  # noqa: E402
from study_qb_assistant.search import LocalQuestionIndex  # noqa: E402


class QueryAdmissionApiTests(unittest.TestCase):
    def test_api_and_ocs_overload_responses_keep_their_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "study-qb.sqlite3"
            auth = AuthService(database_path)
            platform = PlatformServices(database_path)
            client = TestClient(
                create_app(
                    AnswerService(LocalQuestionIndex(())),
                    auth_service=auth,
                    platform_services=platform,
                    require_auth=True,
                )
            )
            client.post(
                "/api/v1/auth/register",
                json={"username": "owner", "password": "password123"},
            )
            login = client.post(
                "/api/v1/auth/login",
                json={"username": "owner", "password": "password123"},
            )
            session_headers = {"Authorization": f"Bearer {login.json()['token']}"}
            token = client.post(
                "/api/v1/tokens",
                json={"description": "admission-test"},
                headers=session_headers,
            ).json()["token"]

            config = client.patch(
                "/api/v1/system-config",
                json={
                    "query_rate_limit_enabled": "false",
                    "query_max_active_requests": "1",
                    "query_max_active_requests_per_user": "1",
                },
                headers=session_headers,
            )
            self.assertTrue(config.json()["ok"])

            lease, decision = client.app.state.query_admission.try_acquire(
                "synthetic:holder",
                {
                    "query_rate_limit_enabled": "false",
                    "query_max_active_requests": "1",
                    "query_max_active_requests_per_user": "1",
                },
            )
            self.assertTrue(decision.allowed)
            try:
                standard = client.get(
                    "/api/v1/query",
                    params={"title": "并发保护测试题", "type": "single"},
                    headers=session_headers,
                )
                ocs = client.get(
                    "/ocs/query",
                    params={"title": "并发保护测试题", "type": "single"},
                    headers={"Authorization": f"Bearer {token}"},
                )
                status = client.get("/api/v1/status", headers=session_headers)
            finally:
                lease.release()

        self.assertEqual(standard.status_code, 429)
        self.assertEqual(standard.json()["error"]["code"], "RATE_LIMITED")
        self.assertEqual(standard.headers["retry-after"], "1")
        self.assertEqual(ocs.status_code, 429)
        self.assertEqual(ocs.json()["code"], 1)
        self.assertEqual(ocs.json()["data"]["ai"]["error_code"], "RATE_LIMITED")
        self.assertIn("query_protection", status.json())
        self.assertEqual(status.json()["query_protection"]["configured_global_limit"], 1)


if __name__ == "__main__":
    unittest.main()
