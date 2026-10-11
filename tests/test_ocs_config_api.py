"""OCS 导入配置各出口与 POST 输入边界的集成回归。"""

from __future__ import annotations

import base64
import io
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from study_qb_assistant.api.app import create_app
from study_qb_assistant.auth import AuthService
from study_qb_assistant.platform.container import PlatformServices
from study_qb_assistant.questions.models import QueryResult
from study_qb_assistant.search import LocalQuestionIndex


class CapturingIndex(LocalQuestionIndex):
    """捕获实际路由解析的查询，不调用外部模型或下载图片。"""

    def __init__(self) -> None:
        super().__init__(())
        self.queries = []

    def query(self, query, *, allow_fuzzy=True):
        self.queries.append(query)
        return QueryResult(
            ok=True,
            query=query,
            candidate_answer="B",
            answer_text="其他选项",
            explanation="路由回归夹具",
            confidence=0.99,
            resolution_mode="exact_match",
            review_required=False,
        )


class OcsConfigApiTests(unittest.TestCase):
    """所有复制/分享出口必须使用同一版本配置，损坏引用不能进入答题。"""

    def test_config_exports_and_post_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.sqlite3"
            index = CapturingIndex()
            auth = AuthService(database)
            platform = PlatformServices(database)
            with TestClient(
                create_app(
                    index,
                    auth_service=auth,
                    platform_services=platform,
                    require_auth=True,
                )
            ) as client:
                registered = client.post(
                    "/api/v1/auth/register",
                    json={"username": "owner", "password": "test-password123"},
                )
                self.assertEqual(registered.status_code, 200)
                login = client.post(
                    "/api/v1/auth/login",
                    json={"username": "owner", "password": "test-password123"},
                )
                headers = {"Authorization": f"Bearer {login.json()['token']}"}
                created = client.post(
                    "/api/v1/tokens", json={"description": "回归配置"}, headers=headers
                )
                self.assertEqual(created.status_code, 200)
                raw_token = created.json()["token"]
                selected = client.get("/api/v1/tokens/ocs-config", headers=headers)
                self.assertEqual(selected.status_code, 200)
                self.assertEqual(selected.headers["cache-control"], "no-store")
                generic = client.get("/api/v1/configs/ocs-local-study-bank.json")
                shared = client.get("/api/v1/shares/apikey-template")
                builtin = client.get(
                    "/api/v1/import-scripts/ocs_local_question_bank", headers=headers
                )
                configs = (
                    created.json()["ocs_config"],
                    selected.json()["ocs_config"],
                    generic.json(),
                    shared.json()["ocs_config"],
                    builtin.json()["script"]["ocs_config"],
                )
                for config in configs:
                    item = config[0]
                    self.assertEqual(item["v"], 2)
                    self.assertEqual(item["method"], "post")
                    self.assertEqual(item["headers"]["Content-Type"], "application/json")
                    self.assertEqual(item["data"], configs[0][0]["data"])
                self.assertEqual(
                    selected.json()["ocs_config"][0]["headers"]["Authorization"],
                    f"Bearer {raw_token}",
                )
                self.assertEqual(
                    shared.json()["ocs_config"][0]["headers"]["Authorization"], "Bearer {{TOKEN}}"
                )
                denied = client.post("/ocs/query", json={"title": "示例题"})
                self.assertEqual(denied.status_code, 401)

                buffer = io.BytesIO()
                Image.new("RGB", (16, 16), "red").save(buffer, format="PNG")
                image = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode(
                    "ascii"
                )
                key_headers = {"Authorization": f"Bearer {raw_token}"}
                for payload in (
                    {"title": "[图片2]", "image_data_urls": [image]},
                    {"title": "[图片1]", "image_data_urls": ["invalid"]},
                    {"title": "原文", "raw_text": "冲突题干"},
                    {
                        "title": "[图片1] https://cdn.example.test/failed.svg",
                        "image_data_urls": [image],
                    },
                ):
                    with self.subTest(title=payload["title"]):
                        response = client.post("/ocs/query", json=payload, headers=key_headers)
                        self.assertEqual(response.status_code, 400)
                        self.assertEqual(
                            response.json()["data"]["ai"]["error_code"], "INVALID_INPUT"
                        )
                        self.assertIsNone(response.json()["data"]["answer"])
                self.assertEqual(index.queries, [])
                bad_get = client.get("/ocs/query", params={"title": "[图片1]"}, headers=key_headers)
                self.assertEqual(bad_get.status_code, 400)
                self.assertEqual(bad_get.json()["data"]["ai"]["error_code"], "INVALID_INPUT")
                valid = client.post(
                    "/ocs/query",
                    json={
                        "title": "[图片2]",
                        "options": "A. 正确\nB. 其他选项",
                        "type": "single",
                        "image_data_urls": [image, image],
                    },
                    headers=key_headers,
                )
                self.assertEqual(valid.status_code, 200)
                self.assertEqual(valid.json()["code"], 0)
                self.assertEqual(index.queries[-1].title, "[图片1]")
                self.assertEqual(index.queries[-1].image_data_urls, (image,))


if __name__ == "__main__":
    unittest.main()
