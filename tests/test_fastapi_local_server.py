"""FastAPI route tests for the local service boundary."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.answering import AnswerService  # noqa: E402
from study_qb_assistant.api.local_server import create_app  # noqa: E402
from study_qb_assistant.auth import AuthService  # noqa: E402
from study_qb_assistant.logger import log_path  # noqa: E402
from study_qb_assistant.models import CanonicalQuestionRecord, ModelAnswer, QuestionQuery  # noqa: E402
from study_qb_assistant.platform import PlatformService  # noqa: E402
from study_qb_assistant.search import LocalQuestionIndex  # noqa: E402
from study_qb_assistant.storage import database as database_module  # noqa: E402
from study_qb_assistant.storage.question_repository import SqlAlchemyQuestionRepository  # noqa: E402


class LowConfidenceProvider:
    """用于接口测试的低置信度模型提供者。"""

    provider_name = "low-confidence-provider"

    def answer(self, query: QuestionQuery) -> ModelAnswer:
        """返回结构化但低置信度的答案。"""

        return ModelAnswer("A", "公私合营", f"低置信度解析：{query.title}", 0.43)


class FastAPILocalServerTests(unittest.TestCase):
    """Covers route behavior that used to live in the hand-written HTTP handler."""

    @staticmethod
    def _runtime_database_path(directory: str) -> Path:
        """为测试场景生成统一的 SQLite 运行时数据库路径。"""
        return Path(directory) / "study-qb.sqlite3"

    def test_query_and_ocs_routes_keep_existing_wire_shape(self) -> None:
        import os

        os.environ["STQB_OCS_API_KEYS"] = "wire-shape-key"
        try:
            client = TestClient(create_app(_sample_index(), require_auth=False))
            key_headers = {"Authorization": "Bearer wire-shape-key"}

            health = client.get("/healthz")
            query_get = client.get(
                "/query", params={"title": "示例题", "type": "single"}, headers=key_headers
            )
            query_post = client.post(
                "/query",
                json={
                    "title": "示例题",
                    "options": ["正确项", "干扰项"],
                    "type": "single",
                    "request_id": "route-test",
                },
                headers=key_headers,
            )
            ocs_get = client.get(
                "/ocs/query", params={"title": "示例题", "type": "single"}, headers=key_headers
            )
            config = client.get("/configs/ocs-local-study-bank.json")
        finally:
            os.environ.pop("STQB_OCS_API_KEYS", None)

        self.assertEqual(health.json(), {"ok": True})
        self.assertEqual(query_get.json()["result"]["candidate_answer"], "A")
        self.assertEqual(query_post.json()["request_id"], "route-test")
        self.assertEqual(ocs_get.json()["code"], 0)
        self.assertEqual(ocs_get.json()["data"]["answer"], "A")
        self.assertEqual(config.json()[0]["data"]["title"], "${title}")

    def test_spa_route_fallback_serves_frontend_for_browser_navigation(self) -> None:
        client = TestClient(create_app(_sample_index(), require_auth=True))

        page = client.get("/users", headers={"Accept": "text/html"})
        tokens_page = client.get(
            "/tokens",
            headers={"Accept": "*/*", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"},
        )
        future_page = client.get("/future-admin-page", headers={"Accept": "text/html"})
        future_api = client.get("/future-api", headers={"Accept": "application/json"})
        missing_asset = client.get("/assets/missing.js", headers={"Accept": "*/*"})
        missing_api = client.get("/auth/missing", headers={"Accept": "application/json"})

        self.assertEqual(page.status_code, 200)
        self.assertIn("text/html", page.headers["content-type"])
        self.assertIn("<!doctype html", page.text.lower())
        self.assertEqual(tokens_page.status_code, 200)
        self.assertIn("text/html", tokens_page.headers["content-type"])
        self.assertEqual(future_page.status_code, 200)
        self.assertIn("text/html", future_page.headers["content-type"])
        self.assertEqual(future_api.status_code, 404)
        self.assertEqual(future_api.json()["error"]["code"], "NOT_FOUND")
        self.assertEqual(missing_asset.status_code, 404)
        self.assertEqual(missing_asset.json()["error"]["code"], "NOT_FOUND")
        self.assertEqual(missing_api.status_code, 404)
        self.assertEqual(missing_api.json()["error"]["code"], "NOT_FOUND")

    def test_tokens_api_keeps_json_for_non_navigation_requests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            auth = AuthService(database_path)
            platform = PlatformService(database_path)
            client = TestClient(
                create_app(
                    _sample_index(), auth_service=auth, platform_service=platform, require_auth=True
                )
            )

            client.post("/auth/register", json={"username": "tester", "password": "password123"})
            login = client.post(
                "/auth/login",
                json={"username": "tester", "password": "password123"},
            )
            token = login.json()["token"]
            response = client.get(
                "/tokens",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "*/*",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Dest": "empty",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ok"], True)
        self.assertIn("tokens", response.json())

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
            client = TestClient(
                create_app(
                    _sample_index(), auth_service=auth, platform_service=platform, require_auth=True
                )
            )

            register = client.post(
                "/auth/register", json={"username": "owner", "password": "password123"}
            )
            login = client.post(
                "/auth/login", json={"username": "owner", "password": "password123"}
            )
            token = login.json()["token"]
            headers = {"Authorization": f"Bearer {token}"}

            me = client.get("/users/me", headers=headers)
            token_create = client.post("/tokens", json={"description": "我的 OCS"}, headers=headers)
            token_list = client.get("/tokens", headers=headers)
            usage_before = client.get("/usage-logs", headers=headers)

            raw_api_token = token_create.json()["token"]
            ocs_headers = {"Authorization": f"Bearer {raw_api_token}"}
            query = client.get(
                "/ocs/query", params={"title": "示例题", "type": "single"}, headers=ocs_headers
            )
            usage_after = client.get("/usage-logs", headers=headers)
            workbench_after_query = client.get("/dashboard/workbench", headers=headers)
            unused_token_create = client.post(
                "/tokens", json={"description": "未使用 OCS"}, headers=headers
            )
            usage_by_token = client.get(
                "/usage-logs",
                params={"token_id": token_create.json()["token_info"]["token_id"]},
                headers=headers,
            )
            usage_by_legacy_api_key_id = client.get(
                "/usage-logs",
                params={"api_key_id": token_create.json()["token_info"]["token_id"]},
                headers=headers,
            )
            usage_by_unused_token = client.get(
                "/usage-logs",
                params={"token_id": unused_token_create.json()["token_info"]["token_id"]},
                headers=headers,
            )

            feedback = client.post(
                "/feedback",
                json={
                    "category": "wrong_answer",
                    "title": "答错了",
                    "content": "这题答案不对",
                    "image_urls": ["https://example.com/a.png"],
                },
                headers=headers,
            )
            feedback_list = client.get("/feedback", headers=headers)
            feedback_id = feedback.json()["feedback"]["feedback_id"]
            points_before_feedback_resolve = client.get("/users/me", headers=headers)
            feedback_resolve = client.patch(
                f"/feedback/{feedback_id}",
                json={
                    "status": "resolved",
                    "admin_note": "已修正题库",
                    "corrected_answer": "B",
                    "reward_points": 20,
                },
                headers=headers,
            )
            feedback_list_after_resolve = client.get("/feedback", headers=headers)
            points_after_feedback_resolve = client.get("/users/me", headers=headers)
            feedback_resolve_repeat = client.patch(
                f"/feedback/{feedback_id}",
                json={
                    "status": "resolved",
                    "admin_note": "重复保存",
                    "corrected_answer": "B",
                    "reward_points": 20,
                },
                headers=headers,
            )
            points_after_feedback_repeat = client.get("/users/me", headers=headers)
            billing_get = client.get("/billing", headers=headers)
            billing_patch = client.patch("/billing", json={"llm_fallback": 9}, headers=headers)
            wallet_me = client.get("/wallet/me", headers=headers)
            wallet_orders_after_feedback = client.get("/wallet/orders", headers=headers)
            redeem_code_create = client.post(
                "/wallet/redeem-codes",
                json={"kind": "points", "points": 25, "max_uses": 1},
                headers=headers,
            )
            subscription_code_rejected = client.post(
                "/wallet/redeem-codes",
                json={"kind": "subscription", "subscription_days": 30, "max_uses": 1},
                headers=headers,
            )
            subscription_grant_rejected = client.post(
                "/wallet/grants",
                json={"username": "owner", "kind": "subscription", "subscription_days": 30},
                headers=headers,
            )
            redeem = client.post(
                "/wallet/redeem",
                json={"code": redeem_code_create.json()["redeem_code"]["code"]},
                headers=headers,
            )
            wallet_orders_after = client.get("/wallet/orders", headers=headers)
            system_config_patch = client.patch(
                "/system-config",
                json={
                    "smart_proto_enabled": "false",
                    "custom_proto_header": "https",
                    "default_user_points": "150",
                    "invite_bonus_points": "30",
                    "manual_grant_default_points": "88",
                    "redeem_code_default_points": "66",
                },
                headers=headers,
            )
            system_config_get = client.get("/system-config", headers=headers)
            ocs_config_after_proto_change = client.get(
                "/configs/ocs-local-study-bank.json",
                headers={**headers, "Host": "example.com"},
            )
            points_policy_get = client.get("/points-policy", headers=headers)
            llm_model_create = client.post(
                "/llm-models",
                json={
                    "name": "主力模型",
                    "base_url": "https://llm.example.com/v1",
                    "model": "gpt-test",
                    "api_key": "model-secret-key",
                    "role": "primary",
                },
                headers=headers,
            )
            llm_models = client.get("/llm-models", headers=headers)
            
            # 测试模型连通性测试接口（未登录拦截验证）
            model_id_for_test = llm_models.json()["models"][0]["model_id"]
            # 创建一个全新的未授权客户端来检验 401 拦截（因为 client 原有 Cookie 缓存了之前的会话）
            unauth_client = TestClient(client.app)
            blocked_test = unauth_client.post(f"/llm-models/{model_id_for_test}/test")
            self.assertEqual(blocked_test.status_code, 401)
            
            # 使用超级管理员进行连通性测试调用（因 mock，连接被拦截或失败是预期结果，主要验证逻辑链路畅通）
            test_response = client.post(f"/llm-models/{model_id_for_test}/test", headers=headers)
            self.assertIn("ok", test_response.json())
            
            platform.save_llm_call_trace(
                {
                    "request_id": "req-evidence",
                    "phase": "web_search",
                    "model_id": "duckduckgo",
                    "model_name": "DuckDuckGo",
                    "evidence": [
                        {
                            "title": "证据标题",
                            "url": "https://example.com/evidence",
                            "snippet": "证据摘要",
                        }
                    ],
                }
            )
            llm_traces = client.get("/llm-traces", headers=headers)
            plain_register = client.post(
                "/auth/register",
                json={"username": "plain", "password": "password123"},
            )
            invited_register = client.post(
                "/auth/register",
                json={
                    "username": "invited",
                    "password": "password123",
                    "invite_code": "demo-code",
                },
            )

        self.assertTrue(register.json()["ok"])
        self.assertTrue(me.json()["ok"])
        self.assertEqual(me.json()["user"]["role"], "superadmin")
        self.assertTrue(token_create.json()["ok"])
        self.assertIsInstance(token_create.json()["ocs_config"], list)
        self.assertEqual(token_create.json()["ocs_config"][0]["type"], "GM_xmlhttpRequest")
        self.assertEqual(len(token_list.json()["tokens"]), 1)
        self.assertEqual(len(usage_before.json()["logs"]), 0)
        self.assertEqual(query.status_code, 200)
        self.assertGreaterEqual(len(usage_after.json()["logs"]), 1)
        self.assertGreater(usage_after.json()["logs"][0]["elapsed_ms"], 0)
        self.assertTrue(usage_after.json()["logs"][0]["request_id"])
        self.assertTrue(usage_after.json()["logs"][0]["provider"])
        self.assertNotEqual(
            workbench_after_query.json()["workbench"]["overview"]["avg_response_seconds"], 0.82
        )
        self.assertEqual(usage_by_token.json()["total"], 1)
        self.assertEqual(usage_by_legacy_api_key_id.json()["total"], 1)
        self.assertEqual(usage_by_unused_token.json()["total"], 0)
        self.assertTrue(feedback.json()["ok"])
        self.assertEqual(feedback.json()["feedback"]["category"], "wrong_answer")
        self.assertEqual(len(feedback_list.json()["feedbacks"]), 1)
        self.assertEqual(feedback_list.json()["feedbacks"][0]["category"], "wrong_answer")
        self.assertTrue(feedback_resolve.json()["ok"])
        self.assertEqual(feedback_resolve.json()["granted_points"], 20)
        resolved_feedback = feedback_list_after_resolve.json()["feedbacks"][0]
        self.assertEqual(resolved_feedback["admin_note"], "已修正题库")
        self.assertEqual(resolved_feedback["corrected_answer"], "B")
        self.assertEqual(resolved_feedback["reward_points"], 20)
        self.assertEqual(resolved_feedback["handled_by"], "owner")
        self.assertGreater(resolved_feedback["handled_at"], 0)
        self.assertEqual(
            points_after_feedback_resolve.json()["user"]["points"],
            points_before_feedback_resolve.json()["user"]["points"] + 20,
        )
        self.assertEqual(feedback_resolve_repeat.json()["granted_points"], 0)
        self.assertEqual(
            points_after_feedback_repeat.json()["user"]["points"],
            points_after_feedback_resolve.json()["user"]["points"],
        )
        self.assertEqual(billing_get.json()["billing"]["llm_fallback"], 3)
        self.assertEqual(billing_patch.json()["billing"]["llm_fallback"], 9)
        self.assertTrue(wallet_me.json()["ok"])
        self.assertNotIn("subscription_active", wallet_me.json()["wallet"])
        self.assertNotIn("subscription_expires_at", wallet_me.json()["wallet"])
        self.assertEqual(len(wallet_orders_after_feedback.json()["orders"]), 1)
        self.assertEqual(wallet_orders_after_feedback.json()["orders"][0]["source"], "feedback_reward")
        self.assertEqual(wallet_orders_after_feedback.json()["orders"][0]["points_delta"], 20)
        self.assertNotIn("subscription_days", redeem_code_create.json()["redeem_code"])
        self.assertEqual(subscription_code_rejected.status_code, 422)
        self.assertEqual(subscription_grant_rejected.status_code, 422)
        self.assertTrue(redeem.json()["ok"])
        self.assertGreaterEqual(len(wallet_orders_after.json()["orders"]), 2)
        self.assertNotIn("subscription_days", wallet_orders_after.json()["orders"][0])
        self.assertFalse(system_config_patch.json()["reload_required"])
        self.assertEqual(system_config_get.json()["config"]["smart_proto_enabled"], "false")
        self.assertEqual(system_config_get.json()["config"]["custom_proto_header"], "https")
        self.assertNotIn("llm_base_url", system_config_get.json()["config"])
        self.assertNotIn("ai_cache_enabled", system_config_get.json()["config"])
        self.assertIn("https://example.com/ocs/query", ocs_config_after_proto_change.text)
        self.assertEqual(system_config_get.json()["config"]["default_user_points"], "150")
        self.assertEqual(points_policy_get.json()["points_policy"]["manual_grant_default_points"], 88)
        self.assertEqual(points_policy_get.json()["points_policy"]["redeem_code_default_points"], 66)
        self.assertTrue(llm_model_create.json()["model"]["api_key_configured"])
        self.assertEqual(llm_model_create.json()["model"]["api_key"], "******")
        self.assertTrue(llm_models.json()["models"][0]["api_key_configured"])
        self.assertEqual(llm_models.json()["models"][0]["api_key"], "******")
        self.assertEqual(llm_traces.json()["traces"][0]["evidence"][0]["title"], "证据标题")
        self.assertEqual(plain_register.json()["user"]["points"], 150)
        self.assertEqual(invited_register.json()["user"]["points"], 180)

    def test_admin_can_manage_users_but_regular_user_cannot_patch_billing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            auth = AuthService(database_path)
            platform = PlatformService(database_path)
            client = TestClient(
                create_app(
                    _sample_index(), auth_service=auth, platform_service=platform, require_auth=True
                )
            )

            client.post("/auth/register", json={"username": "boss", "password": "password123"})
            super_headers = {
                "Authorization": f"Bearer {client.post('/auth/login', json={'username': 'boss', 'password': 'password123'}).json()['token']}"
            }
            client.post("/auth/register", json={"username": "alice", "password": "password123"})
            client.post("/auth/register", json={"username": "bob", "password": "password123"})
            promote_admin = client.patch(
                "/users/alice", json={"role": "admin"}, headers=super_headers
            )
            admin_headers = {
                "Authorization": f"Bearer {client.post('/auth/login', json={'username': 'alice', 'password': 'password123'}).json()['token']}"
            }
            user_headers = {
                "Authorization": f"Bearer {client.post('/auth/login', json={'username': 'bob', 'password': 'password123'}).json()['token']}"
            }

            users = client.get("/users", headers=admin_headers)
            patch_points_ok = client.patch(
                "/users/bob", json={"points": 250}, headers=admin_headers
            )
            patch_role_forbidden = client.patch(
                "/users/bob", json={"role": "admin"}, headers=admin_headers
            )
            patch_forbidden = client.patch("/billing", json={"local_hit": 5}, headers=user_headers)
            system_forbidden = client.patch(
                "/system-config", json={"llm_model": "x"}, headers=admin_headers
            )
            redeem_code_create = client.post(
                "/wallet/redeem-codes",
                json={"kind": "points", "points": 10, "max_uses": 1},
                headers=admin_headers,
            )
            wallet_grant_ok = client.post(
                "/wallet/grants",
                json={"username": "bob", "kind": "points", "points": 5},
                headers=admin_headers,
            )
            wallet_grant_admin_forbidden = client.post(
                "/wallet/grants",
                json={"username": "alice", "kind": "points", "points": 5},
                headers=admin_headers,
            )
            disable_ok = client.patch(
                "/users/bob", json={"status": "disabled"}, headers=admin_headers
            )

        self.assertEqual(promote_admin.status_code, 200)
        self.assertEqual(users.status_code, 200)
        self.assertEqual(len(users.json()["users"]), 3)
        self.assertEqual(patch_points_ok.json()["user"]["points"], 250)
        self.assertEqual(patch_role_forbidden.status_code, 403)
        self.assertEqual(patch_forbidden.status_code, 403)
        self.assertEqual(system_forbidden.status_code, 403)
        self.assertEqual(redeem_code_create.status_code, 200)
        self.assertEqual(wallet_grant_ok.status_code, 200)
        self.assertEqual(wallet_grant_admin_forbidden.status_code, 403)
        self.assertEqual(
            wallet_grant_admin_forbidden.json()["error"]["message"],
            "管理员只能为普通用户发放积分",
        )
        self.assertEqual(disable_ok.json()["user"]["status"], "disabled")

    def test_admin_can_list_and_update_questions_but_regular_user_cannot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            auth = AuthService(database_path)
            platform = PlatformService(database_path)

            record = CanonicalQuestionRecord(
                question_id="http_q_1",
                title_raw="HTTP题目",
                question_type="single",
                options_raw=("A", "B"),
                answer_raw="A",
                explanation="None",
                subject="general",
                chapter=None,
                tags=(),
                source_name="TestSource",
                source_url="",
                source_license="",
                source_split="",
                source_record_path="",
            )
            index = LocalQuestionIndex((record,))

            client = TestClient(
                create_app(index, auth_service=auth, platform_service=platform, require_auth=True)
            )

            client.post("/auth/register", json={"username": "boss", "password": "password123"})
            super_headers = {
                "Authorization": f"Bearer {client.post('/auth/login', json={'username': 'boss', 'password': 'password123'}).json()['token']}"
            }
            client.post("/auth/register", json={"username": "alice", "password": "password123"})
            client.post("/auth/register", json={"username": "bob", "password": "password123"})

            client.patch("/users/alice", json={"role": "admin"}, headers=super_headers)

            admin_headers = {
                "Authorization": f"Bearer {client.post('/auth/login', json={'username': 'alice', 'password': 'password123'}).json()['token']}"
            }
            user_headers = {
                "Authorization": f"Bearer {client.post('/auth/login', json={'username': 'bob', 'password': 'password123'}).json()['token']}"
            }

            res_user_list = client.get("/questions", headers=user_headers)
            self.assertEqual(res_user_list.status_code, 403)

            res_admin_list = client.get("/questions", headers=admin_headers)
            self.assertEqual(res_admin_list.status_code, 200)
            self.assertEqual(res_admin_list.json()["total"], 1)
            self.assertEqual(res_admin_list.json()["questions"][0]["title_raw"], "HTTP题目")

            res_user_patch = client.patch(
                "/questions/http_q_1",
                json={"title_raw": "新标题", "answer_raw": "B"},
                headers=user_headers,
            )
            self.assertEqual(res_user_patch.status_code, 403)

            res_admin_patch = client.patch(
                "/questions/http_q_1",
                json={"title_raw": "新标题", "answer_raw": "B"},
                headers=admin_headers,
            )
            self.assertEqual(res_admin_patch.status_code, 200)
            self.assertEqual(res_admin_patch.json()["question"]["title_raw"], "新标题")
            self.assertEqual(res_admin_patch.json()["question"]["answer_raw"], "B")

            res_reloaded_list = client.get("/questions", headers=admin_headers)
            self.assertEqual(res_reloaded_list.json()["questions"][0]["title_raw"], "新标题")

            res_user_delete = client.delete("/questions/http_q_1", headers=user_headers)
            self.assertEqual(res_user_delete.status_code, 403)

            res_admin_delete = client.delete("/questions/http_q_1", headers=admin_headers)
            self.assertEqual(res_admin_delete.status_code, 200)
            self.assertTrue(res_admin_delete.json()["ok"])
            self.assertEqual(res_admin_delete.json()["status"], "deleted")

            res_deleted_list = client.get("/questions", headers=admin_headers)
            self.assertEqual(res_deleted_list.json()["total"], 0)
            self.assertFalse(index.query(QuestionQuery(title="新标题", question_type="single")).ok)

            res_repeat_delete = client.delete("/questions/http_q_1", headers=admin_headers)
            self.assertEqual(res_repeat_delete.status_code, 200)
            self.assertEqual(res_repeat_delete.json()["status"], "deleted")

            res_missing_delete = client.delete("/questions/missing", headers=admin_headers)
            self.assertEqual(res_missing_delete.status_code, 404)
            self.assertEqual(res_missing_delete.json()["error"]["code"], "QUESTION_NOT_FOUND")

    def test_completion_request_ignores_noisy_options_in_get(self) -> None:
        import os

        os.environ["STQB_OCS_API_KEYS"] = "noisy-get-key"
        try:
            client = TestClient(create_app(_sample_index(), require_auth=False))
            response = client.get(
                "/ocs/query",
                params={
                    "title": "填空题(1分)1992年，邓小平发表【1】____，对整个社会主义现代化建设事业产生了重大而深远的影响。",
                    "type": "completion",
                    "options": "}#loadEditorAnswerd(405113364, 2);#answerContentChange();#});",
                },
                headers={"Authorization": "Bearer noisy-get-key"},
            )
        finally:
            os.environ.pop("STQB_OCS_API_KEYS", None)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["answer"], "南方谈话")

    def test_completion_request_ignores_noisy_options_in_post(self) -> None:
        import os

        os.environ["STQB_OCS_API_KEYS"] = "noisy-post-key"
        try:
            client = TestClient(create_app(_sample_index(), require_auth=False))
            response = client.post(
                "/ocs/query",
                json={
                    "title": "填空题(1分)社会主义本质是解放生产力、发展生产力，消灭剥削，消除两极分化，最终达到【1】____。",
                    "type": "completion",
                    "options": [
                        "}",
                        "loadEditorAnswerd(405113366, 2);",
                        "answerContentChange();",
                        "});",
                    ],
                },
                headers={"Authorization": "Bearer noisy-post-key"},
            )
        finally:
            os.environ.pop("STQB_OCS_API_KEYS", None)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["answer"], "共同富裕")

    def test_multi_blank_completion_response_matches_ocs_split_contract(self) -> None:
        import os

        os.environ["STQB_OCS_API_KEYS"] = "multi-blank-key"
        try:
            client = TestClient(create_app(_sample_index(), require_auth=False))
            response = client.get(
                "/ocs/query",
                params={
                    "title": "填空题(2分)第一空【1】____，第二空【2】____。",
                    "type": "completion",
                    "options": "}#loadEditorAnswerd(405113370, 2);#answerContentChange();#});",
                },
                headers={"Authorization": "Bearer multi-blank-key"},
            )
        finally:
            os.environ.pop("STQB_OCS_API_KEYS", None)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["answer"], '["第一空答案", "第二空答案"]')

    def test_llm_runtime_config_uses_llm_cache_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            auth = AuthService(database_path)
            platform = PlatformService(database_path)
            client = TestClient(
                create_app(
                    _sample_index(), auth_service=auth, platform_service=platform, require_auth=True
                )
            )

            client.post("/auth/register", json={"username": "boss", "password": "password123"})
            headers = {
                "Authorization": f"Bearer {client.post('/auth/login', json={'username': 'boss', 'password': 'password123'}).json()['token']}"
            }

            initial = client.get("/llm-runtime-config", headers=headers)
            update = client.patch(
                "/llm-runtime-config",
                json={
                    "llm_cache_enabled": "false",
                    "llm_cache_min_confidence": "0.98",
                    "llm_cache_min_confirmations": "3",
                    "ai_cache_enabled": "true",
                },
                headers=headers,
            )

        self.assertTrue(initial.json()["ok"])
        self.assertIn("llm_cache_enabled", initial.json()["config"])
        self.assertNotIn("ai_cache_enabled", initial.json()["config"])
        self.assertTrue(update.json()["ok"])
        self.assertEqual(update.json()["config"]["llm_cache_enabled"], "false")
        self.assertEqual(update.json()["config"]["llm_cache_min_confidence"], "0.98")
        self.assertEqual(update.json()["config"]["llm_cache_min_confirmations"], "3")
        self.assertNotIn("ai_cache_enabled", update.json()["config"])

    def test_llm_runtime_config_persists_web_search_configs_without_leaking_keys(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            auth = AuthService(database_path)
            platform = PlatformService(database_path)
            client = TestClient(
                create_app(
                    _sample_index(), auth_service=auth, platform_service=platform, require_auth=True
                )
            )

            client.post("/auth/register", json={"username": "boss", "password": "password123"})
            headers = {
                "Authorization": f"Bearer {client.post('/auth/login', json={'username': 'boss', 'password': 'password123'}).json()['token']}"
            }
            search_configs = [
                {
                    "id": "search_google",
                    "name": "Google",
                    "provider": "google",
                    "api_key": "google-secret",
                    "cx": "cx-001",
                    "proxy_url": "http://127.0.0.1:7890",
                    "status": "active",
                }
            ]

            update = client.patch(
                "/llm-runtime-config",
                json={"web_search_configs": json.dumps(search_configs, ensure_ascii=False)},
                headers=headers,
            )
            response_config = json.loads(update.json()["config"]["web_search_configs"])
            raw_config = json.loads(
                platform.get_llm_runtime_config(reveal_secret=True)["web_search_configs"]
            )
            edit_without_secret = [
                {
                    "id": "search_google",
                    "name": "Google Edited",
                    "provider": "google",
                    "api_key": "",
                    "api_key_configured": True,
                    "cx": "cx-002",
                    "proxy_url": "",
                    "status": "active",
                }
            ]
            preserved = client.patch(
                "/llm-runtime-config",
                json={"web_search_configs": json.dumps(edit_without_secret, ensure_ascii=False)},
                headers=headers,
            )
            preserved_raw_config = json.loads(
                platform.get_llm_runtime_config(reveal_secret=True)["web_search_configs"]
            )

        self.assertTrue(update.json()["ok"])
        self.assertEqual(response_config[0]["provider"], "google")
        self.assertNotIn("api_key", response_config[0])
        self.assertTrue(response_config[0]["api_key_configured"])
        self.assertEqual(raw_config[0]["api_key"], "google-secret")
        self.assertTrue(preserved.json()["ok"])
        self.assertEqual(preserved_raw_config[0]["api_key"], "google-secret")
        self.assertEqual(preserved_raw_config[0]["cx"], "cx-002")

    def test_workbench_script_notification_and_catalog_routes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            auth = AuthService(database_path)
            platform = PlatformService(database_path)
            client = TestClient(
                create_app(
                    _sample_index(), auth_service=auth, platform_service=platform, require_auth=True
                )
            )

            client.post("/auth/register", json={"username": "boss", "password": "password123"})
            headers = {
                "Authorization": f"Bearer {client.post('/auth/login', json={'username': 'boss', 'password': 'password123'}).json()['token']}"
            }

            token_create = client.post(
                "/tokens", json={"description": "工作台接入"}, headers=headers
            )
            token_id = token_create.json()["token_info"]["token_id"]
            notify = platform.create_notification(
                user_id=None,
                level="info",
                category="system",
                title="系统公告",
                content="接口稳定性优化完成",
            )

            integrations_removed = client.get("/integrations", headers=headers)
            integration_create_removed = client.post(
                "/integrations",
                json={
                    "name": "旧接入点",
                    "platform": "ocs",
                    "base_url": "https://example.com/ocs",
                    "token_id": token_id,
                    "status": "active",
                    "description": "已下线功能不再提供接口",
                },
                headers=headers,
            )
            import_script = client.post(
                "/import-scripts/generate",
                json={
                    "name": "生活活系统导入",
                    "token_id": token_id,
                    "target": "ocs",
                    "include_test_snippet": True,
                },
                headers=headers,
            )
            script_id = import_script.json()["script"]["script_id"]
            quota_package_create = client.post(
                "/quota-packages",
                json={"name": "基础套餐", "kind": "points", "points": 1000},
                headers=headers,
            )
            roles_before_update = client.get("/roles", headers=headers)
            role_update = client.put(
                "/roles/admin/permissions",
                json={"permissions": ["dashboard:all", "users:write", "questions:read"]},
                headers=headers,
            )
            invalid_role_update = client.put(
                "/roles/admin/permissions",
                json={"permissions": ["integrations:write"]},
                headers=headers,
            )

            workbench = client.get("/dashboard/workbench", headers=headers)
            rankings = client.get("/dashboard/rankings", headers=headers)
            notifications = client.get("/notifications", headers=headers)
            notification_read = client.post(
                f"/notifications/{notify['notification_id']}/read", headers=headers
            )
            scripts = client.get("/import-scripts", headers=headers)
            script_detail = client.get(f"/import-scripts/{script_id}", headers=headers)
            default_script_detail = client.get(
                "/import-scripts/ocs_local_question_bank", headers=headers
            )
            missing_script_detail = client.get("/import-scripts/not-found", headers=headers)
            default_script_delete = client.delete(
                "/import-scripts/ocs_local_question_bank", headers=headers
            )
            quota_packages = client.get("/quota-packages", headers=headers)
            roles = client.get("/roles", headers=headers)
            role_detail = client.get("/roles/admin/permissions", headers=headers)

        self.assertTrue(workbench.json()["ok"])
        self.assertIn("hero", workbench.json()["workbench"])
        self.assertTrue(rankings.json()["ok"])
        self.assertTrue(notifications.json()["ok"])
        self.assertEqual(notification_read.json()["notification"]["read"], True)
        self.assertEqual(integrations_removed.status_code, 404)
        self.assertIn(integration_create_removed.status_code, {404, 405})
        admin_actions = {item["key"] for item in workbench.json()["workbench"]["quick_actions"]}
        self.assertNotIn("test_integration", admin_actions)
        self.assertNotIn("integration_manage", admin_actions)
        self.assertTrue(scripts.json()["ok"])
        default_scripts = [
            item for item in scripts.json()["scripts"] if item.get("script_id") == "ocs_local_question_bank"
        ]
        self.assertEqual(len(default_scripts), 1)
        self.assertTrue(default_scripts[0]["builtin"])
        self.assertTrue(default_scripts[0]["is_default"])
        self.assertEqual(script_detail.json()["script"]["target"], "ocs")
        self.assertTrue(default_script_detail.json()["script"]["builtin"])
        self.assertIn("/ocs/query", default_script_detail.json()["script"]["content"])
        self.assertEqual(missing_script_detail.status_code, 404)
        self.assertEqual(missing_script_detail.json()["error"]["code"], "SCRIPT_NOT_FOUND")
        self.assertEqual(default_script_delete.status_code, 400)
        self.assertEqual(
            default_script_delete.json()["error"]["code"], "BUILTIN_SCRIPT_READONLY"
        )
        self.assertEqual(quota_package_create.status_code, 405)
        self.assertEqual(quota_packages.status_code, 404)
        self.assertTrue(roles_before_update.json()["ok"])
        admin_defaults = next(
            item for item in roles_before_update.json()["roles"] if item["role_id"] == "admin"
        )
        self.assertIn("llm:read", admin_defaults["permissions"])
        self.assertIn("wallet:changes:read", admin_defaults["permissions"])
        self.assertTrue(roles.json()["ok"])
        self.assertEqual(role_update.json()["role"]["role_id"], "admin")
        self.assertIn("questions:read", role_detail.json()["role"]["permissions"])
        self.assertEqual(invalid_role_update.status_code, 400)
        self.assertEqual(invalid_role_update.json()["error"]["code"], "INVALID_PERMISSION")

    def test_user_workbench_actions_hide_admin_entries_and_expose_copy_script(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            auth = AuthService(database_path)
            platform = PlatformService(database_path)
            client = TestClient(
                create_app(
                    _sample_index(), auth_service=auth, platform_service=platform, require_auth=True
                )
            )

            client.post("/auth/register", json={"username": "boss", "password": "password123"})
            client.post("/auth/register", json={"username": "alice", "password": "password123"})
            user_headers = {
                "Authorization": f"Bearer {client.post('/auth/login', json={'username': 'alice', 'password': 'password123'}).json()['token']}"
            }

            workbench = client.get("/dashboard/workbench", headers=user_headers)

        self.assertTrue(workbench.json()["ok"])
        actions = {item["key"] for item in workbench.json()["workbench"]["quick_actions"]}
        self.assertIn("copy_import_script", actions)
        self.assertNotIn("generate_script", actions)
        self.assertNotIn("test_integration", actions)
        self.assertNotIn("integration_manage", actions)
        self.assertEqual(workbench.json()["workbench"]["overview"]["avg_response_seconds"], 0.0)

    def test_workbench_average_response_uses_recorded_elapsed_ms(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            auth = AuthService(database_path)
            platform = PlatformService(database_path)
            client = TestClient(
                create_app(
                    _sample_index(), auth_service=auth, platform_service=platform, require_auth=True
                )
            )

            client.post("/auth/register", json={"username": "boss", "password": "password123"})
            client.post("/auth/register", json={"username": "alice", "password": "password123"})
            user_headers = {
                "Authorization": f"Bearer {client.post('/auth/login', json={'username': 'alice', 'password': 'password123'}).json()['token']}"
            }
            alice_user_id = auth.get_user("alice")["user_id"]
            platform.record_usage(
                user_id=alice_user_id,
                username="alice",
                token_id=None,
                title="第一题",
                question_type="single",
                resolution_mode="local_hit",
                answer="A",
                confidence=1.0,
                provider="local",
                points_cost=1,
                elapsed_ms=1000.0,
            )
            platform.record_usage(
                user_id=alice_user_id,
                username="alice",
                token_id=None,
                title="第二题",
                question_type="single",
                resolution_mode="local_hit",
                answer="B",
                confidence=1.0,
                provider="local",
                points_cost=1,
                elapsed_ms=3000.0,
            )

            workbench = client.get("/dashboard/workbench", headers=user_headers)

        self.assertTrue(workbench.json()["ok"])
        overview = workbench.json()["workbench"]["overview"]
        self.assertEqual(overview["today_calls"], 2)
        self.assertEqual(overview["avg_response_seconds"], 2.0)

    def test_usage_logs_date_filters_follow_shanghai_natural_day_and_validate_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            auth = AuthService(database_path)
            platform = PlatformService(database_path)
            client = TestClient(
                create_app(
                    _sample_index(), auth_service=auth, platform_service=platform, require_auth=True
                )
            )

            client.post("/auth/register", json={"username": "alice", "password": "password123"})
            alice_headers = {
                "Authorization": f"Bearer {client.post('/auth/login', json={'username': 'alice', 'password': 'password123'}).json()['token']}"
            }
            user = auth.get_user("alice")
            target_day = "2026-06-27"
            next_day = "2026-06-28"
            end_of_day = datetime(2026, 6, 27, 23, 59, 59, 999000, tzinfo=ZoneInfo("Asia/Shanghai"))
            next_day_start = datetime(2026, 6, 28, 0, 0, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
            platform.record_usage(
                user_id=user["user_id"],
                username="alice",
                token_id=None,
                title="自然日尾部题目",
                question_type="single",
                resolution_mode="local_hit",
                answer="A",
                confidence=1.0,
                provider="local",
                points_cost=0,
                elapsed_ms=120.0,
            )
            platform.record_usage(
                user_id=user["user_id"],
                username="alice",
                token_id=None,
                title="次日零点题目",
                question_type="single",
                resolution_mode="local_hit",
                answer="B",
                confidence=1.0,
                provider="local",
                points_cost=0,
                elapsed_ms=160.0,
            )
            with platform.repository.session_factory() as session:
                first_log = session.execute(
                    text(
                        """
                        SELECT log_id FROM usage_logs
                        WHERE username = 'alice'
                        ORDER BY created_at ASC
                        LIMIT 1
                        """
                    )
                ).scalar_one()
                second_log = session.execute(
                    text(
                        """
                        SELECT log_id FROM usage_logs
                        WHERE username = 'alice'
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                    )
                ).scalar_one()
                session.execute(
                    text("UPDATE usage_logs SET created_at = :created_at WHERE log_id = :log_id"),
                    {"created_at": end_of_day.timestamp(), "log_id": first_log},
                )
                session.execute(
                    text("UPDATE usage_logs SET created_at = :created_at WHERE log_id = :log_id"),
                    {"created_at": next_day_start.timestamp(), "log_id": second_log},
                )
                session.commit()

            target_response = client.get(
                "/usage-logs",
                params={"start_date": target_day, "end_date": target_day},
                headers=alice_headers,
            )
            next_day_response = client.get(
                "/usage-logs",
                params={"start_date": next_day, "end_date": next_day},
                headers=alice_headers,
            )
            invalid_response = client.get(
                "/usage-logs",
                params={"start_date": "2026-06-xx"},
                headers=alice_headers,
            )

        self.assertEqual(target_response.status_code, 200)
        self.assertEqual(target_response.json()["total"], 1)
        self.assertEqual(target_response.json()["logs"][0]["title"], "自然日尾部题目")
        self.assertEqual(next_day_response.status_code, 200)
        self.assertEqual(next_day_response.json()["total"], 1)
        self.assertEqual(next_day_response.json()["logs"][0]["title"], "次日零点题目")
        self.assertEqual(invalid_response.status_code, 400)
        self.assertEqual(invalid_response.json()["error"]["code"], "INVALID_DATE")

    def test_debug_recent_tolerates_bad_log_lines_and_validates_date_format(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            log_file = Path(directory) / "service.jsonl"
            with mock.patch.dict(
                "os.environ",
                {"STQB_LOG_PATH": str(log_file)},
                clear=False,
            ):
                auth = AuthService(database_path)
                platform = PlatformService(database_path)
                client = TestClient(
                    create_app(
                        _sample_index(),
                        auth_service=auth,
                        platform_service=platform,
                        require_auth=True,
                    )
                )
                client.post("/auth/register", json={"username": "owner", "password": "password123"})
                owner_headers = {
                    "Authorization": f"Bearer {client.post('/auth/login', json={'username': 'owner', 'password': 'password123'}).json()['token']}"
                }

                path = log_path()
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("wb") as handle:
                    handle.write(
                        b'{"ts":"2026-06-27T08:00:00+08:00","event":"query","title":"ok"}\n'
                    )
                    handle.write(b'{"ts":"2026-06-27T08:01:00+08:00","event":"query"\n')
                    handle.write(b'\xff\xfe\xfd\n')
                    handle.write(
                        b'{"ts":"2026-06-28T08:00:00+08:00","event":"query","title":"next"}\n'
                    )

                valid_response = client.get(
                    "/debug/recent",
                    params={"start_date": "2026-06-27", "end_date": "2026-06-27"},
                    headers=owner_headers,
                )
                invalid_response = client.get(
                    "/debug/recent",
                    params={"start_date": "bad-date"},
                    headers=owner_headers,
                )

        self.assertEqual(valid_response.status_code, 200)
        self.assertTrue(valid_response.json()["ok"])
        self.assertEqual(len(valid_response.json()["events"]), 1)
        self.assertEqual(valid_response.json()["events"][0]["title"], "ok")
        self.assertEqual(invalid_response.status_code, 400)
        self.assertEqual(invalid_response.json()["error"]["code"], "INVALID_DATE")

    def test_record_usage_is_atomic_when_usage_log_commit_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            auth = AuthService(database_path)
            platform = PlatformService(database_path)
            user = auth.register("alice", "password123")
            auth.set_points("alice", 25)

            with mock.patch.object(
                platform.repository,
                "commit_usage_transaction",
                side_effect=RuntimeError("write failed"),
            ):
                with self.assertRaises(RuntimeError):
                    platform.record_usage(
                        user_id=user["user_id"],
                        username="alice",
                        token_id=None,
                        title="失败题目",
                        question_type="single",
                        resolution_mode="local_hit",
                        answer="A",
                        confidence=1.0,
                        provider="local",
                        points_cost=3,
                        elapsed_ms=88.0,
                    )

            current_user = auth.get_user("alice")
            logs = platform.list_usage_logs(username="alice")

        self.assertEqual(current_user["points"], 25)
        self.assertEqual(len(logs), 0)

    def test_token_quota_rejection_keeps_points_and_counters_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            auth = AuthService(database_path)
            platform = PlatformService(database_path)
            client = TestClient(
                create_app(
                    _sample_index(), auth_service=auth, platform_service=platform, require_auth=True
                )
            )

            client.post("/auth/register", json={"username": "alice", "password": "password123"})
            auth.set_points("alice", 10)
            alice_headers = {
                "Authorization": f"Bearer {client.post('/auth/login', json={'username': 'alice', 'password': 'password123'}).json()['token']}"
            }
            token_res = client.post(
                "/tokens",
                json={"description": "quota", "quota_limit": 1},
                headers=alice_headers,
            )
            raw_token = token_res.json()["token"]
            token_id = token_res.json()["token_info"]["token_id"]
            first = client.get(
                "/ocs/query",
                params={"title": "示例题", "type": "single"},
                headers={"Authorization": f"Bearer {raw_token}"},
            )
            points_after_first = auth.get_user("alice")["points"]
            second = client.get(
                "/ocs/query",
                params={"title": "示例题", "type": "single"},
                headers={"Authorization": f"Bearer {raw_token}"},
            )
            points_after_second = auth.get_user("alice")["points"]
            token_after = next(
                item
                for item in platform.list_tokens(user_id=auth.get_user("alice")["user_id"])
                if item["token_id"] == token_id
            )
            logs = platform.list_usage_logs(username="alice")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 401)
        self.assertEqual(second.json()["error"]["code"], "TOKEN_QUOTA_EXCEEDED")
        self.assertEqual(points_after_first, 9)
        self.assertEqual(points_after_second, 9)
        self.assertEqual(token_after["usage_count"], 1)
        self.assertEqual(token_after["quota_used"], 1)
        self.assertEqual(len(logs), 1)

    def test_legacy_usage_logs_table_gets_elapsed_ms_compat_column(self) -> None:
        engine = create_engine("sqlite:///:memory:", future=True)
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE usage_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        log_id VARCHAR(64) UNIQUE,
                        user_id VARCHAR(64),
                        username VARCHAR(64),
                        token_id VARCHAR(64),
                        title TEXT,
                        question_type VARCHAR(64),
                        resolution_mode VARCHAR(64),
                        answer TEXT,
                        confidence FLOAT DEFAULT 0.0,
                        points_cost INTEGER DEFAULT 0,
                        provider VARCHAR(128) DEFAULT '',
                        created_at FLOAT
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO usage_logs (
                        log_id, user_id, username, token_id, title, question_type,
                        resolution_mode, answer, confidence, points_cost, provider, created_at
                    )
                    VALUES (
                        'legacy-log', 'legacy-user', 'legacy', NULL, '旧题目', 'single',
                        'local_hit', 'A', 1.0, 1, 'local', 1.0
                    )
                    """
                )
            )
        database_module.ensure_sqlite_compat_columns(engine)
        with engine.connect() as connection:
            columns = {
                row[1] for row in connection.execute(text("PRAGMA table_info(usage_logs)")).fetchall()
            }
            elapsed_ms = connection.execute(
                text("SELECT elapsed_ms FROM usage_logs WHERE log_id = 'legacy-log'")
            ).scalar_one()
        engine.dispose()

        self.assertIn("elapsed_ms", columns)
        self.assertEqual(elapsed_ms, 0.0)

    def test_dashboard_rankings_user_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            auth = AuthService(database_path)
            platform = PlatformService(database_path)
            client = TestClient(
                create_app(
                    _sample_index(), auth_service=auth, platform_service=platform, require_auth=True
                )
            )

            # 1. Register superadmin (owner) and create a log
            client.post("/auth/register", json={"username": "owner", "password": "password123"})
            owner_login = client.post(
                "/auth/login", json={"username": "owner", "password": "password123"}
            )
            owner_token = owner_login.json()["token"]
            owner_headers = {"Authorization": f"Bearer {owner_token}"}

            # Create token and query to generate a log for owner
            token_res = client.post(
                "/tokens", json={"description": "Owner Token"}, headers=owner_headers
            )
            raw_token = token_res.json()["token"]
            client.get(
                "/ocs/query",
                params={"title": "Test Question", "type": "single"},
                headers={"Authorization": f"Bearer {raw_token}"},
            )

            # 2. Register normal user (alice) who has no usage logs
            client.post("/auth/register", json={"username": "alice", "password": "password123"})
            alice_login = client.post(
                "/auth/login", json={"username": "alice", "password": "password123"}
            )
            alice_token = alice_login.json()["token"]
            alice_headers = {"Authorization": f"Bearer {alice_token}"}

            # 3. Query workbench and rankings for owner (superadmin) -> should see the log
            owner_workbench = client.get("/dashboard/workbench", headers=owner_headers)
            owner_rankings = client.get("/dashboard/rankings", headers=owner_headers)
            self.assertTrue(owner_workbench.json()["ok"])
            self.assertTrue(owner_rankings.json()["ok"])
            self.assertGreater(len(owner_workbench.json()["workbench"]["ranking_preview"]), 0)
            self.assertGreater(len(owner_rankings.json()["rankings"]), 0)

            # 4. Query workbench and rankings for alice (normal user) -> should be empty
            alice_workbench = client.get("/dashboard/workbench", headers=alice_headers)
            alice_rankings = client.get("/dashboard/rankings", headers=alice_headers)
            self.assertTrue(alice_workbench.json()["ok"])
            self.assertTrue(alice_rankings.json()["ok"])
            self.assertEqual(len(alice_workbench.json()["workbench"]["ranking_preview"]), 0)
            self.assertEqual(len(alice_rankings.json()["rankings"]), 0)

    def test_dashboard_scope_defaults_and_admin_can_switch_between_global_and_self(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            auth = AuthService(database_path)
            platform = PlatformService(database_path)
            client = TestClient(
                create_app(
                    _sample_index(), auth_service=auth, platform_service=platform, require_auth=True
                )
            )

            client.post("/auth/register", json={"username": "owner", "password": "password123"})
            client.post("/auth/register", json={"username": "alice", "password": "password123"})
            owner_headers = {
                "Authorization": f"Bearer {client.post('/auth/login', json={'username': 'owner', 'password': 'password123'}).json()['token']}"
            }
            alice_headers = {
                "Authorization": f"Bearer {client.post('/auth/login', json={'username': 'alice', 'password': 'password123'}).json()['token']}"
            }

            owner_token = client.post(
                "/tokens", json={"description": "owner"}, headers=owner_headers
            ).json()["token"]
            alice_token = client.post(
                "/tokens", json={"description": "alice"}, headers=alice_headers
            ).json()["token"]
            client.get(
                "/ocs/query",
                params={"title": "示例题", "type": "single"},
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            client.get(
                "/ocs/query",
                params={"title": "示例题", "type": "single"},
                headers={"Authorization": f"Bearer {alice_token}"},
            )

            owner_default = client.get("/dashboard/workbench", headers=owner_headers)
            owner_self = client.get("/dashboard/workbench", params={"scope": "self"}, headers=owner_headers)
            alice_global = client.get(
                "/dashboard/summary",
                params={"scope": "global", "days": 1},
                headers=alice_headers,
            )

        self.assertEqual(owner_default.status_code, 200)
        self.assertEqual(owner_default.json()["workbench"]["scope"], "global")
        self.assertEqual(owner_default.json()["workbench"]["overview"]["today_calls"], 2)
        self.assertEqual(owner_self.json()["workbench"]["scope"], "self")
        self.assertEqual(owner_self.json()["workbench"]["overview"]["today_calls"], 1)
        self.assertEqual(alice_global.json()["summary"]["scope"], "self")
        self.assertEqual(alice_global.json()["summary"]["query_count"], 1)

    def test_usage_audit_reports_usage_logs_token_totals_and_runtime_log_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            auth = AuthService(database_path)
            platform = PlatformService(database_path)
            client = TestClient(
                create_app(
                    _sample_index(), auth_service=auth, platform_service=platform, require_auth=True
                )
            )

            client.post("/auth/register", json={"username": "owner", "password": "password123"})
            owner_headers = {
                "Authorization": f"Bearer {client.post('/auth/login', json={'username': 'owner', 'password': 'password123'}).json()['token']}"
            }
            raw_token = client.post(
                "/tokens", json={"description": "owner"}, headers=owner_headers
            ).json()["token"]
            client.get(
                "/ocs/query",
                params={"title": "示例题", "type": "single"},
                headers={"Authorization": f"Bearer {raw_token}"},
            )
            date_text = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
            audit = client.get("/debug/usage-audit", params={"date": date_text}, headers=owner_headers)

        self.assertEqual(audit.status_code, 200)
        self.assertTrue(audit.json()["ok"])
        self.assertEqual(audit.json()["audit"]["usage_logs"]["count"], 1)
        self.assertEqual(audit.json()["audit"]["api_tokens"]["usage_count_total"], 1)
        self.assertEqual(audit.json()["audit"]["api_tokens"]["quota_used_total"], 1)
        self.assertFalse(audit.json()["audit"]["api_tokens"]["daily_count_available"])
        self.assertGreaterEqual(audit.json()["audit"]["runtime_logs"]["query_event_count"], 1)

    def test_api_key_quota_limits_and_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            auth = AuthService(database_path)
            platform = PlatformService(database_path)
            client = TestClient(
                create_app(
                    _sample_index(), auth_service=auth, platform_service=platform, require_auth=True
                )
            )

            # 1. Register and login superadmin and a normal user
            client.post("/auth/register", json={"username": "owner", "password": "password123"})
            client.post("/auth/register", json={"username": "alice", "password": "password123"})
            auth.set_points("alice", 100)
            alice_login = client.post(
                "/auth/login", json={"username": "alice", "password": "password123"}
            )
            alice_token = alice_login.json()["token"]
            alice_headers = {"Authorization": f"Bearer {alice_token}"}

            # 2. Create token with quota_limit = 2
            token_res = client.post(
                "/tokens",
                json={"description": "Test Limit Key", "quota_limit": 2},
                headers=alice_headers,
            )
            self.assertTrue(token_res.json()["ok"])
            token_id = token_res.json()["token_info"]["token_id"]
            raw_token = token_res.json()["token"]
            self.assertEqual(token_res.json()["token_info"]["quota_limit"], 2)
            self.assertEqual(token_res.json()["token_info"]["quota_used"], 0)

            # 3. Call OCS query once
            query_headers = {"Authorization": f"Bearer {raw_token}"}
            q1 = client.get(
                "/ocs/query", params={"title": "示例题", "type": "single"}, headers=query_headers
            )
            self.assertEqual(q1.status_code, 200)

            # Check token info -> quota_used should be 1
            tokens_after = client.get("/tokens", headers=alice_headers)
            target_token = next(
                t for t in tokens_after.json()["tokens"] if t["token_id"] == token_id
            )
            self.assertEqual(target_token["quota_used"], 1)
            self.assertEqual(target_token["usage_count"], 1)

            # 4. Call OCS query a second time -> still allowed
            q2 = client.get(
                "/ocs/query", params={"title": "示例题", "type": "single"}, headers=query_headers
            )
            self.assertEqual(q2.status_code, 200)

            tokens_after_second = client.get("/tokens", headers=alice_headers)
            target_token_after_second = next(
                t for t in tokens_after_second.json()["tokens"] if t["token_id"] == token_id
            )
            self.assertEqual(target_token_after_second["quota_used"], 2)
            self.assertEqual(target_token_after_second["usage_count"], 2)

            # 5. 第三次请求应被额度拦截
            q3 = client.get(
                "/ocs/query", params={"title": "示例题", "type": "single"}, headers=query_headers
            )
            self.assertEqual(q3.status_code, 401)
            self.assertEqual(q3.json()["error"]["code"], "TOKEN_QUOTA_EXCEEDED")

            # 6. Update token quota_limit to 5
            update_res = client.post(
                f"/tokens/{token_id}",
                json={"description": "Updated Limit Key", "quota_limit": 5},
                headers=alice_headers,
            )
            self.assertTrue(update_res.json()["ok"])
            self.assertEqual(update_res.json()["token"]["quota_limit"], 5)

            # 7. Call OCS query again -> should work now
            q4 = client.get(
                "/ocs/query", params={"title": "示例题", "type": "single"}, headers=query_headers
            )
            self.assertEqual(q4.status_code, 200)

            # 8. Delete token
            del_res = client.delete(f"/tokens/{token_id}", headers=alice_headers)
            self.assertTrue(del_res.json()["ok"])

            # 9. Listing tokens -> deleted token should be gone
            tokens_final = client.get("/tokens", headers=alice_headers)
            self.assertEqual(len(tokens_final.json()["tokens"]), 0)

            # 10. Query OCS using deleted token -> should return 401 (invalid key)
            q5 = client.get(
                "/ocs/query", params={"title": "示例题", "type": "single"}, headers=query_headers
            )
            self.assertEqual(q5.status_code, 401)

    def test_token_import_script_requires_token_or_returns_template(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            auth = AuthService(database_path)
            platform = PlatformService(database_path)
            client = TestClient(
                create_app(
                    _sample_index(), auth_service=auth, platform_service=platform, require_auth=True
                )
            )

            client.post("/auth/register", json={"username": "boss", "password": "password123"})
            headers = {
                "Authorization": f"Bearer {client.post('/auth/login', json={'username': 'boss', 'password': 'password123'}).json()['token']}"
            }

            no_token = client.get("/tokens/import-script", headers=headers)
            token_a = client.post("/tokens", json={"description": "A"}, headers=headers)
            one_token = client.get("/tokens/import-script", headers=headers)
            token_b = client.post("/tokens", json={"description": "B"}, headers=headers)
            multiple_tokens = client.get("/tokens/import-script", headers=headers)
            direct = client.get(
                "/tokens/import-script",
                params={"token_id": token_b.json()["token_info"]["token_id"]},
                headers=headers,
            )

        self.assertEqual(no_token.status_code, 404)
        self.assertEqual(no_token.json()["error"]["code"], "TOKEN_REQUIRED")
        self.assertEqual(token_a.status_code, 200)
        self.assertEqual(one_token.json()["mode"], "direct")
        self.assertEqual(one_token.json()["template_id"], "ocs_local_question_bank")
        self.assertIn("{{TOKEN}}", one_token.json()["script"])
        self.assertIn("/ocs/query", one_token.json()["script"])
        self.assertIsInstance(one_token.json()["ocs_config"], list)
        self.assertEqual(one_token.json()["ocs_config"][0]["type"], "GM_xmlhttpRequest")
        self.assertIn("/ocs/query", one_token.json()["ocs_config"][0]["url"])
        self.assertEqual(token_b.status_code, 200)
        self.assertEqual(multiple_tokens.json()["mode"], "select_token")
        self.assertEqual(len(multiple_tokens.json()["token_options"]), 2)
        self.assertEqual(direct.json()["mode"], "direct")
        self.assertEqual(
            direct.json()["token_id"],
            token_b.json()["token_info"]["token_id"],
        )

    def test_runtime_index_loads_reviewed_records_from_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            auth = AuthService(database_path)
            platform = PlatformService(database_path)
            repository = SqlAlchemyQuestionRepository(database_path)
            repository.save_question_record(
                CanonicalQuestionRecord(
                    question_id="reviewed:1",
                    title_raw="单选题(1分)运行时应能加载数据库评审题。",
                    question_type="single",
                    options_raw=("答案一", "答案二"),
                    answer_raw="B",
                    explanation="人工评审答案。",
                    subject="reviewed",
                    chapter=None,
                    tags=("chaoxing_reviewed",),
                    source_name="ChaoxingReviewed",
                    source_url="",
                    source_license="user-local-reviewed",
                    source_split="reviewed",
                    source_record_path="tests",
                )
            )
            client = TestClient(
                create_app(
                    LocalQuestionIndex(()),
                    auth_service=auth,
                    platform_service=platform,
                    require_auth=False,
                )
            )

            response = client.get(
                "/query",
                params={
                    "title": "单选题(1分)运行时应能加载数据库评审题。",
                    "options": "答案一#答案二",
                    "type": "single",
                },
            )

        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["result"]["candidate_answer"], "B")
        self.assertEqual(response.json()["sources"][0]["source_name"], "ChaoxingReviewed")

    def test_deleted_database_record_is_not_restored_from_startup_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            auth = AuthService(database_path)
            platform = PlatformService(database_path)
            record = CanonicalQuestionRecord(
                question_id="jsonl:deleted",
                title_raw="单选题(1分)已删除题不应重启复活。",
                question_type="single",
                options_raw=("会复活", "不会复活"),
                answer_raw="B",
                explanation="删除后应保留墓碑状态。",
                subject="verified",
                chapter=None,
                tags=("verified",),
                source_name="VerifiedJsonl",
                source_url="",
                source_license="local",
                source_split="verified",
                source_record_path="verified.jsonl",
            )
            repository = SqlAlchemyQuestionRepository(database_path)
            repository.save_question_record(record)
            repository.soft_delete_question_record(record.question_id)

            client = TestClient(
                create_app(
                    LocalQuestionIndex((record,)),
                    auth_service=auth,
                    platform_service=platform,
                    require_auth=False,
                )
            )
            response = client.get(
                "/query",
                params={
                    "title": "单选题(1分)已删除题不应重启复活。",
                    "options": "会复活#不会复活",
                    "type": "single",
                },
            )
            reloaded = SqlAlchemyQuestionRepository(database_path).get_question_record(
                record.question_id
            )

        self.assertFalse(response.json()["ok"])
        self.assertEqual(response.json()["error"]["code"], "NOT_FOUND")
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.to_dict()["status"], "deleted")

    def test_reviewed_record_overrides_ai_generated_duplicate_on_startup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            auth = AuthService(database_path)
            platform = PlatformService(database_path)
            repository = SqlAlchemyQuestionRepository(database_path)
            repository.save_question_record(
                CanonicalQuestionRecord(
                    question_id="reviewed:dup",
                    title_raw="单选题(1分)同题应优先使用评审题库。",
                    question_type="single",
                    options_raw=("正确项", "干扰项"),
                    answer_raw="A",
                    explanation="人工评审答案。",
                    subject="reviewed",
                    chapter=None,
                    tags=("chaoxing_reviewed",),
                    source_name="ChaoxingReviewed",
                    source_url="",
                    source_license="user-local-reviewed",
                    source_split="reviewed",
                    source_record_path="tests",
                )
            )
            ai_seed = LocalQuestionIndex(
                (
                    CanonicalQuestionRecord(
                        question_id="ai:dup",
                        title_raw="单选题(1分)同题应优先使用评审题库。",
                        question_type="single",
                        options_raw=("正确项", "干扰项"),
                        answer_raw="B",
                        explanation="旧 AI 答案。",
                        subject="ai-generated",
                        chapter=None,
                        tags=("ai_generated", "auto_learned"),
                        source_name="AIGenerated",
                        source_url="",
                        source_license="user-local-ai-generated",
                        source_split="trusted",
                        source_record_path="tests",
                        metadata={
                            "record_origin": "ai_generated",
                            "ai_status": "trusted",
                            "ai_confidence": "0.99",
                        },
                    ),
                )
            )
            client = TestClient(
                create_app(
                    ai_seed,
                    auth_service=auth,
                    platform_service=platform,
                    require_auth=False,
                )
            )

            response = client.get(
                "/query",
                params={
                    "title": "单选题(1分)同题应优先使用评审题库。",
                    "options": "正确项#干扰项",
                    "type": "single",
                },
            )

        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["result"]["candidate_answer"], "A")
        self.assertEqual(response.json()["sources"][0]["source_name"], "ChaoxingReviewed")

    def test_ocs_query_can_hide_low_confidence_answer_by_token_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            auth = AuthService(database_path)
            platform = PlatformService(database_path)
            lookup = AnswerService(
                LocalQuestionIndex(()),
                model_provider=LowConfidenceProvider(),
                allow_model_fallback=True,
            )
            client = TestClient(
                create_app(lookup, auth_service=auth, platform_service=platform, require_auth=True)
            )

            client.post("/auth/register", json={"username": "owner", "password": "password123"})
            session = client.post(
                "/auth/login", json={"username": "owner", "password": "password123"}
            )
            headers = {"Authorization": f"Bearer {session.json()['token']}"}
            token_create = client.post(
                "/tokens",
                json={
                    "description": "严格拒答",
                    "reject_low_confidence": True,
                    "min_answer_confidence": 0.8,
                },
                headers=headers,
            )
            raw_api_token = token_create.json()["token"]

            response = client.get(
                "/ocs/query",
                params={
                    "title": "单选题(1分)国家资本主义的高级形式是【1】____。",
                    "options": "公私合营#农业互助组",
                    "type": "single",
                },
                headers={"Authorization": f"Bearer {raw_api_token}"},
            )
            questions = client.get(
                "/questions",
                params={"keyword": "公私合营", "status": "low_confidence"},
                headers=headers,
            )

        self.assertTrue(token_create.json()["token_info"]["reject_low_confidence"])
        self.assertEqual(token_create.json()["token_info"]["min_answer_confidence"], 0.8)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 1)
        self.assertIsNone(response.json()["data"]["answer"])
        self.assertEqual(response.json()["data"]["ai"]["error_code"], "LOW_CONFIDENCE_ANSWER")
        self.assertEqual(questions.json()["total"], 1)


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
