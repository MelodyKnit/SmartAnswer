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
from study_qb_assistant.platform import PlatformService  # noqa: E402
from study_qb_assistant.search import LocalQuestionIndex  # noqa: E402


class FastAPILocalServerTests(unittest.TestCase):
    """Covers route behavior that used to live in the hand-written HTTP handler."""

    @staticmethod
    def _runtime_database_path(directory: str) -> Path:
        """为测试场景生成统一的 SQLite 运行时数据库路径。"""
        return Path(directory) / "study-qb.sqlite3"

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
            auth = AuthService(self._runtime_database_path(directory))
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

    def test_user_token_billing_usage_and_feedback_flow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            auth = AuthService(database_path)
            platform = PlatformService(database_path)
            client = TestClient(create_app(_sample_index(), auth_service=auth, platform_service=platform, require_auth=True))

            register = client.post("/auth/register", json={"username": "owner", "password": "password123"})
            login = client.post("/auth/login", json={"username": "owner", "password": "password123"})
            token = login.json()["token"]
            headers = {"Authorization": f"Bearer {token}"}

            me = client.get("/users/me", headers=headers)
            token_create = client.post("/tokens", json={"description": "我的 OCS"}, headers=headers)
            token_list = client.get("/tokens", headers=headers)
            usage_before = client.get("/usage-logs", headers=headers)

            raw_api_token = token_create.json()["token"]
            ocs_headers = {"Authorization": f"Bearer {raw_api_token}"}
            query = client.get("/ocs/query", params={"title": "示例题", "type": "single"}, headers=ocs_headers)
            usage_after = client.get("/usage-logs", headers=headers)

            feedback = client.post(
                "/feedback",
                json={"title": "答错了", "content": "这题答案不对", "image_urls": ["https://example.com/a.png"]},
                headers=headers,
            )
            feedback_list = client.get("/feedback", headers=headers)
            billing_get = client.get("/billing", headers=headers)
            billing_patch = client.patch("/billing", json={"llm_fallback": 9}, headers=headers)
            wallet_me = client.get("/wallet/me", headers=headers)
            wallet_orders_before = client.get("/wallet/orders", headers=headers)
            redeem_code_create = client.post(
                "/wallet/redeem-codes",
                json={"kind": "points", "points": 25, "max_uses": 1},
                headers=headers,
            )
            redeem = client.post("/wallet/redeem", json={"code": redeem_code_create.json()["redeem_code"]["code"]}, headers=headers)
            wallet_orders_after = client.get("/wallet/orders", headers=headers)
            system_config_patch = client.patch(
                "/system-config",
                json={"llm_base_url": "https://example.com/v1", "llm_api_key": "secret-key"},
                headers=headers,
            )
            system_config_get = client.get("/system-config", headers=headers)

        self.assertTrue(register.json()["ok"])
        self.assertTrue(me.json()["ok"])
        self.assertEqual(me.json()["user"]["role"], "superadmin")
        self.assertTrue(token_create.json()["ok"])
        self.assertEqual(len(token_list.json()["tokens"]), 1)
        self.assertEqual(len(usage_before.json()["logs"]), 0)
        self.assertEqual(query.status_code, 200)
        self.assertGreaterEqual(len(usage_after.json()["logs"]), 1)
        self.assertTrue(feedback.json()["ok"])
        self.assertEqual(len(feedback_list.json()["feedbacks"]), 1)
        self.assertEqual(billing_get.json()["billing"]["llm_fallback"], 3)
        self.assertEqual(billing_patch.json()["billing"]["llm_fallback"], 9)
        self.assertTrue(wallet_me.json()["ok"])
        self.assertEqual(len(wallet_orders_before.json()["orders"]), 0)
        self.assertTrue(redeem.json()["ok"])
        self.assertGreaterEqual(len(wallet_orders_after.json()["orders"]), 1)
        self.assertFalse(system_config_patch.json()["reload_required"])
        self.assertEqual(system_config_get.json()["config"]["llm_base_url"], "https://example.com/v1")
        self.assertTrue(system_config_get.json()["config"]["llm_api_key_configured"])

    def test_admin_can_manage_users_but_regular_user_cannot_patch_billing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            auth = AuthService(database_path)
            platform = PlatformService(database_path)
            client = TestClient(create_app(_sample_index(), auth_service=auth, platform_service=platform, require_auth=True))

            client.post("/auth/register", json={"username": "boss", "password": "password123"})
            super_headers = {"Authorization": f"Bearer {client.post('/auth/login', json={'username': 'boss', 'password': 'password123'}).json()['token']}"}
            client.post("/auth/register", json={"username": "alice", "password": "password123"})
            client.post("/auth/register", json={"username": "bob", "password": "password123"})
            promote_admin = client.patch("/users/alice", json={"role": "admin"}, headers=super_headers)
            admin_headers = {"Authorization": f"Bearer {client.post('/auth/login', json={'username': 'alice', 'password': 'password123'}).json()['token']}"}
            user_headers = {"Authorization": f"Bearer {client.post('/auth/login', json={'username': 'bob', 'password': 'password123'}).json()['token']}"}

            users = client.get("/users", headers=admin_headers)
            patch_points_ok = client.patch("/users/bob", json={"points": 250}, headers=admin_headers)
            patch_role_forbidden = client.patch("/users/bob", json={"role": "admin"}, headers=admin_headers)
            patch_forbidden = client.patch("/billing", json={"local_hit": 5}, headers=user_headers)
            system_forbidden = client.patch("/system-config", json={"llm_model": "x"}, headers=admin_headers)
            disable_ok = client.patch("/users/bob", json={"status": "disabled"}, headers=admin_headers)

        self.assertEqual(promote_admin.status_code, 200)
        self.assertEqual(users.status_code, 200)
        self.assertEqual(len(users.json()["users"]), 3)
        self.assertEqual(patch_points_ok.json()["user"]["points"], 250)
        self.assertEqual(patch_role_forbidden.status_code, 403)
        self.assertEqual(patch_forbidden.status_code, 403)
        self.assertEqual(system_forbidden.status_code, 403)
        self.assertEqual(disable_ok.json()["user"]["status"], "disabled")

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

    def test_workbench_integration_script_notification_and_catalog_routes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            auth = AuthService(database_path)
            platform = PlatformService(database_path)
            client = TestClient(create_app(_sample_index(), auth_service=auth, platform_service=platform, require_auth=True))

            client.post("/auth/register", json={"username": "boss", "password": "password123"})
            headers = {"Authorization": f"Bearer {client.post('/auth/login', json={'username': 'boss', 'password': 'password123'}).json()['token']}"}

            token_create = client.post("/tokens", json={"description": "工作台接入"}, headers=headers)
            token_id = token_create.json()["token_info"]["token_id"]
            notify = platform.create_notification(
                user_id=None,
                level="info",
                category="system",
                title="系统公告",
                content="接口稳定性优化完成",
            )

            integration_create = client.post(
                "/integrations",
                json={
                    "name": "生活活系统",
                    "platform": "ocs",
                    "base_url": "https://example.com/ocs",
                    "token_id": token_id,
                    "status": "active",
                    "description": "测试接入点",
                },
                headers=headers,
            )
            integration_id = integration_create.json()["integration"]["integration_id"]
            integration_test = client.post(f"/integrations/{integration_id}/test", headers=headers)
            import_script = client.post(
                "/import-scripts/generate",
                json={
                    "name": "生活活系统导入",
                    "integration_id": integration_id,
                    "token_id": token_id,
                    "target": "ocs",
                    "include_test_snippet": True,
                },
                headers=headers,
            )
            script_id = import_script.json()["script"]["script_id"]
            package_create = client.post(
                "/quota-packages",
                json={
                    "name": "基础套餐",
                    "kind": "points",
                    "points": 1000,
                    "price": 19.9,
                    "description": "基础版",
                    "sort_order": 1,
                },
                headers=headers,
            )
            package_id = package_create.json()["package"]["package_id"]
            role_update = client.put(
                "/roles/admin/permissions",
                json={"permissions": ["dashboard:all", "users:write", "integrations:write"]},
                headers=headers,
            )

            workbench = client.get("/dashboard/workbench", headers=headers)
            rankings = client.get("/dashboard/rankings", headers=headers)
            notifications = client.get("/notifications", headers=headers)
            notification_read = client.post(f"/notifications/{notify['notification_id']}/read", headers=headers)
            integrations = client.get("/integrations", headers=headers)
            integration_status = client.get(f"/integrations/{integration_id}/status", headers=headers)
            scripts = client.get("/import-scripts", headers=headers)
            script_detail = client.get(f"/import-scripts/{script_id}", headers=headers)
            packages = client.get("/quota-packages", headers=headers)
            roles = client.get("/roles", headers=headers)
            role_detail = client.get("/roles/admin/permissions", headers=headers)
            package_delete = client.delete(f"/quota-packages/{package_id}", headers=headers)

        self.assertTrue(workbench.json()["ok"])
        self.assertIn("hero", workbench.json()["workbench"])
        self.assertTrue(rankings.json()["ok"])
        self.assertTrue(notifications.json()["ok"])
        self.assertEqual(notification_read.json()["notification"]["read"], True)
        self.assertTrue(integrations.json()["ok"])
        self.assertEqual(len(integrations.json()["integrations"]), 1)
        self.assertTrue(integration_test.json()["ok"])
        self.assertEqual(integration_status.json()["status"]["last_test_status"], "success")
        self.assertTrue(scripts.json()["ok"])
        self.assertEqual(script_detail.json()["script"]["target"], "ocs")
        self.assertTrue(packages.json()["ok"])
        self.assertEqual(len(packages.json()["packages"]), 1)
        self.assertTrue(roles.json()["ok"])
        self.assertEqual(role_update.json()["role"]["role_id"], "admin")
        self.assertIn("integrations:write", role_detail.json()["role"]["permissions"])
        self.assertTrue(package_delete.json()["ok"])


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
