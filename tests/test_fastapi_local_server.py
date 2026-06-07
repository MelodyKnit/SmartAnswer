"""FastAPI route tests for the local service boundary."""

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

from study_qb_assistant.api.local_server import create_app  # noqa: E402
from study_qb_assistant.auth import AuthService  # noqa: E402
from study_qb_assistant.models import CanonicalQuestionRecord  # noqa: E402
from study_qb_assistant.search import LocalQuestionIndex  # noqa: E402


class FastAPILocalServerTests(unittest.TestCase):
    """Covers route behavior that used to live in the hand-written HTTP handler."""

    def test_query_and_ocs_routes_keep_existing_wire_shape(self) -> None:
        client = TestClient(create_app(_sample_index(), require_auth=False))

        health = client.get("/healthz")
        query_get = client.get("/query", params={"title": "示例题", "type": "single"})
        query_post = client.post(
            "/query",
            json={
                "title": "示例题",
                "options": ["正确项", "干扰项"],
                "type": "single",
                "request_id": "route-test",
            },
        )
        ocs_get = client.get("/ocs/query", params={"title": "示例题", "type": "single"})
        config = client.get("/configs/ocs-local-study-bank.json")

        self.assertEqual(health.json(), {"ok": True})
        self.assertEqual(query_get.json()["result"]["candidate_answer"], "A")
        self.assertEqual(query_post.json()["request_id"], "route-test")
        self.assertEqual(ocs_get.json()["code"], 0)
        self.assertEqual(ocs_get.json()["data"]["answer"], "A")
        self.assertEqual(config.json()[0]["data"]["title"], "${title}")

    def test_require_auth_blocks_data_routes_and_allows_registered_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            auth = AuthService(Path(directory) / "users.json")
            client = TestClient(create_app(_sample_index(), auth_service=auth, require_auth=True))

            blocked = client.get("/status")
            registered = client.post(
                "/auth/register",
                json={"username": "tester", "password": "password123"},
            )
            login = client.post(
                "/auth/login",
                json={"username": "tester", "password": "password123"},
            )
            token = login.json()["token"]
            session = client.get("/auth/session", headers={"Authorization": f"Bearer {token}"})
            status = client.get("/status", headers={"Authorization": f"Bearer {token}"})

        self.assertEqual(blocked.status_code, 401)
        self.assertTrue(registered.json()["ok"])
        self.assertTrue(login.json()["ok"])
        self.assertEqual(session.json()["user"]["username"], "tester")
        self.assertTrue(status.json()["ok"])

    def test_ocs_bearer_key_can_bypass_session_when_auth_is_required(self) -> None:
        previous = __import__("os").environ.get("STQB_OCS_API_KEYS")
        __import__("os").environ["STQB_OCS_API_KEYS"] = "local-test-key"
        try:
            client = TestClient(create_app(_sample_index(), require_auth=True))
            response = client.get(
                "/ocs/query",
                params={"title": "示例题", "type": "single"},
                headers={"Authorization": "Bearer local-test-key"},
            )
        finally:
            if previous is None:
                __import__("os").environ.pop("STQB_OCS_API_KEYS", None)
            else:
                __import__("os").environ["STQB_OCS_API_KEYS"] = previous

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["answer"], "A")

    def test_completion_request_ignores_noisy_options_in_get(self) -> None:
        client = TestClient(create_app(_sample_index(), require_auth=False))

        response = client.get(
            "/ocs/query",
            params={
                "title": "填空题(1分)1992年，邓小平发表【1】____，对整个社会主义现代化建设事业产生了重大而深远的影响。",
                "type": "completion",
                "options": "}#loadEditorAnswerd(405113364, 2);#answerContentChange();#});",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["answer"], "南方谈话")

    def test_completion_request_ignores_noisy_options_in_post(self) -> None:
        client = TestClient(create_app(_sample_index(), require_auth=False))

        response = client.post(
            "/ocs/query",
            json={
                "title": "填空题(1分)社会主义本质是解放生产力、发展生产力，消灭剥削，消除两极分化，最终达到【1】____。",
                "type": "completion",
                "options": ["}", "loadEditorAnswerd(405113366, 2);", "answerContentChange();", "});"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["answer"], "共同富裕")

    def test_multi_blank_completion_response_matches_ocs_split_contract(self) -> None:
        client = TestClient(create_app(_sample_index(), require_auth=False))

        response = client.get(
            "/ocs/query",
            params={
                "title": "填空题(2分)第一空【1】____，第二空【2】____。",
                "type": "completion",
                "options": "}#loadEditorAnswerd(405113370, 2);#answerContentChange();#});",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["answer"], '["第一空答案", "第二空答案"]')


def _sample_index() -> LocalQuestionIndex:
    records = (
        CanonicalQuestionRecord(
            question_id="unit:sample:1",
            title_raw="示例题",
            question_type="single",
            options_raw=("正确项", "干扰项"),
            answer_raw="A",
            explanation="测试解析",
            subject="unit",
            chapter=None,
            tags=("unit",),
            source_name="UnitTest",
            source_url="",
            source_license="test-only",
            source_split="test",
            source_record_path="tests",
        ),
        CanonicalQuestionRecord(
            question_id="unit:completion:109",
            title_raw="填空题(1分)1992年，邓小平发表【1】____，对整个社会主义现代化建设事业产生了重大而深远的影响。",
            question_type="completion",
            options_raw=(),
            answer_raw="南方谈话",
            explanation="测试解析",
            subject="unit",
            chapter=None,
            tags=("unit",),
            source_name="UnitTest",
            source_url="",
            source_license="test-only",
            source_split="test",
            source_record_path="tests",
        ),
        CanonicalQuestionRecord(
            question_id="unit:completion:111",
            title_raw="填空题(1分)社会主义本质是解放生产力、发展生产力，消灭剥削，消除两极分化，最终达到【1】____。",
            question_type="completion",
            options_raw=(),
            answer_raw="共同富裕",
            explanation="测试解析",
            subject="unit",
            chapter=None,
            tags=("unit",),
            source_name="UnitTest",
            source_url="",
            source_license="test-only",
            source_split="test",
            source_record_path="tests",
        ),
        CanonicalQuestionRecord(
            question_id="unit:completion:multi",
            title_raw="填空题(2分)第一空【1】____，第二空【2】____。",
            question_type="completion",
            options_raw=(),
            answer_raw='["第一空答案", "第二空答案"]',
            explanation="测试解析",
            subject="unit",
            chapter=None,
            tags=("unit",),
            source_name="UnitTest",
            source_url="",
            source_license="test-only",
            source_split="test",
            source_record_path="tests",
        ),
    )
    return LocalQuestionIndex(records, source_path="unit")


if __name__ == "__main__":
    unittest.main()
