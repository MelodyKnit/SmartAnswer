"""无状态 API Key 分享与运行库存储的接口回归测试。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.api.app import create_app  # noqa: E402
from study_qb_assistant.auth import AuthService  # noqa: E402
from study_qb_assistant.platform.container import PlatformServices  # noqa: E402
from study_qb_assistant.platform.tokens.records import normalize_token_status  # noqa: E402
from study_qb_assistant.search import LocalQuestionIndex  # noqa: E402
from study_qb_assistant.logger.storage import redact  # noqa: E402
from study_qb_assistant.storage import database as database_module  # noqa: E402
from study_qb_assistant.storage.database import get_engine  # noqa: E402


class TokenSharingTests(unittest.TestCase):
    """验证 API Key 原文动作与无状态分享的端到端契约。"""

    def test_unknown_token_status_fails_closed(self) -> None:
        self.assertEqual(normalize_token_status(None), "active")
        self.assertEqual(normalize_token_status("revoked"), "revoked")
        self.assertEqual(normalize_token_status(""), "disabled")
        self.assertEqual(normalize_token_status("unexpected"), "disabled")

    @staticmethod
    def _runtime_database_path(directory: str) -> Path:
        return Path(directory) / "runtime" / "study-qb.sqlite3"

    def _client(self, directory: str) -> tuple[TestClient, AuthService, PlatformServices]:
        database_path = self._runtime_database_path(directory)
        auth = AuthService(database_path)
        platform = PlatformServices(database_path)
        client = TestClient(
            create_app(
                LocalQuestionIndex(()),
                auth_service=auth,
                platform_services=platform,
                require_auth=True,
            )
        )
        return client, auth, platform

    @staticmethod
    def _register_and_login(client: TestClient, username: str) -> dict[str, str]:
        registered = client.post(
            "/api/v1/auth/register",
            json={"username": username, "password": "password123"},
        )
        if registered.status_code not in {200, 201}:
            raise AssertionError(registered.text)
        logged_in = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": "password123"},
        )
        if logged_in.status_code != 200:
            raise AssertionError(logged_in.text)
        return {"Authorization": f"Bearer {logged_in.json()['token']}"}

    def test_new_key_is_recoverable_but_list_and_public_template_are_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client, _auth, _platform = self._client(directory)
            headers = self._register_and_login(client, "owner")
            created = client.post(
                "/api/v1/tokens",
                json={"description": "shareable"},
                headers=headers,
            )
            raw_token = created.json()["token"]
            token_id = created.json()["token_info"]["token_id"]

            listed = client.get("/api/v1/tokens", headers=headers)
            public_json = listed.text
            template = client.get("/api/v1/shares/apikey-template")
            copied = client.post(
                f"/api/v1/tokens/{token_id}/copy-value",
                headers=headers,
            )
            shared = client.post(
                f"/api/v1/tokens/{token_id}/share-link",
                headers=headers,
            )

        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.headers["cache-control"], "no-store")
        self.assertTrue(created.json()["token_info"]["is_recoverable"])
        self.assertEqual(listed.status_code, 200)
        self.assertNotIn(raw_token, public_json)
        self.assertNotIn("token_raw", public_json)
        self.assertEqual(template.status_code, 200)
        self.assertEqual(set(template.json()), {"ok", "ocs_config"})
        self.assertIn("{{TOKEN}}", template.text)
        self.assertNotIn(raw_token, template.text)
        self.assertEqual(template.json()["ocs_config"][0]["headers"]["Authorization"], "Bearer {{TOKEN}}")
        self.assertEqual(copied.status_code, 200)
        self.assertEqual(copied.json(), {"ok": True, "token_id": token_id, "token": raw_token})
        self.assertEqual(copied.headers["cache-control"], "no-store")
        self.assertEqual(shared.status_code, 200)
        self.assertEqual(shared.json()["share_url"], f"http://testserver/share/apikey#key={raw_token}")
        self.assertNotIn("?key=", shared.json()["share_url"])

    def test_copy_and_share_require_owner_and_active_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client, _auth, _platform = self._client(directory)
            owner_headers = self._register_and_login(client, "owner")
            member_headers = self._register_and_login(client, "member")
            created = client.post(
                "/api/v1/tokens",
                json={"description": "owner-only"},
                headers=owner_headers,
            )
            raw_token = created.json()["token"]
            token_id = created.json()["token_info"]["token_id"]

            other_copy = client.post(
                f"/api/v1/tokens/{token_id}/copy-value",
                headers=member_headers,
            )
            other_share = client.post(
                f"/api/v1/tokens/{token_id}/share-link",
                headers=member_headers,
            )
            disabled = client.patch(
                f"/api/v1/tokens/{token_id}/status",
                json={"enabled": False},
                headers=owner_headers,
            )
            disabled_copy = client.post(
                f"/api/v1/tokens/{token_id}/copy-value",
                headers=owner_headers,
            )
            disabled_share = client.post(
                f"/api/v1/tokens/{token_id}/share-link",
                headers=owner_headers,
            )
            disabled_query = client.get(
                "/ocs/query",
                params={"title": "disabled key", "type": "single"},
                headers={"Authorization": f"Bearer {raw_token}"},
            )
            enabled = client.patch(
                f"/api/v1/tokens/{token_id}/status",
                json={"enabled": True},
                headers=owner_headers,
            )
            enabled_copy = client.post(
                f"/api/v1/tokens/{token_id}/copy-value",
                headers=owner_headers,
            )
            revoked = client.post(
                f"/api/v1/tokens/{token_id}/revoke",
                headers=owner_headers,
            )
            revoked_enable = client.patch(
                f"/api/v1/tokens/{token_id}/status",
                json={"enabled": True},
                headers=owner_headers,
            )
            revoked_query = client.get(
                "/ocs/query",
                params={"title": "revoked key", "type": "single"},
                headers={"Authorization": f"Bearer {raw_token}"},
            )

        self.assertEqual(other_copy.status_code, 404)
        self.assertEqual(other_copy.json()["error"]["code"], "TOKEN_NOT_FOUND")
        self.assertEqual(other_share.status_code, 404)
        self.assertEqual(other_share.json()["error"]["code"], "TOKEN_NOT_FOUND")
        self.assertEqual(disabled.status_code, 200)
        self.assertEqual(disabled.json()["token"]["status"], "disabled")
        self.assertEqual(disabled_copy.status_code, 409)
        self.assertEqual(disabled_copy.json()["error"]["code"], "TOKEN_INACTIVE")
        self.assertEqual(disabled_share.status_code, 409)
        self.assertEqual(disabled_share.json()["error"]["code"], "TOKEN_INACTIVE")
        self.assertEqual(disabled_query.status_code, 401)
        self.assertEqual(disabled_query.json()["error"]["code"], "UNAUTHORIZED")
        self.assertEqual(enabled.status_code, 200)
        self.assertEqual(enabled.json()["token"]["status"], "active")
        self.assertEqual(enabled_copy.status_code, 200)
        self.assertEqual(revoked.status_code, 200)
        self.assertEqual(revoked.json()["token"]["status"], "revoked")
        self.assertEqual(revoked_enable.status_code, 409)
        self.assertEqual(revoked_enable.json()["error"]["code"], "TOKEN_REVOKED")
        self.assertEqual(revoked_query.status_code, 401)
        self.assertEqual(revoked_query.json()["error"]["code"], "UNAUTHORIZED")

    def test_legacy_revoked_status_is_not_migrated_to_reenableable_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client, _auth, platform = self._client(directory)
            headers = self._register_and_login(client, "legacy-revoked-owner")
            created = client.post("/api/v1/tokens", json={}, headers=headers)
            token_id = created.json()["token_info"]["token_id"]
            record = platform.tokens.repository.get_token(token_id)
            assert record is not None
            record.status = "revoked"
            platform.tokens.repository.save_token(record)

            listed = client.get("/api/v1/tokens", headers=headers)
            enabled = client.patch(
                f"/api/v1/tokens/{token_id}/status",
                json={"enabled": True},
                headers=headers,
            )

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["tokens"][0]["status"], "revoked")
        self.assertEqual(enabled.status_code, 409)
        self.assertEqual(enabled.json()["error"]["code"], "TOKEN_REVOKED")

    def test_user_api_key_limit_counts_disabled_keys_and_releases_deleted_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client, _auth, _platform = self._client(directory)
            headers = self._register_and_login(client, "limited-owner")
            configured = client.patch(
                "/api/v1/system-config",
                json={"api_key_max_count": "2"},
                headers=headers,
            )
            first = client.post("/api/v1/tokens", json={"description": "one"}, headers=headers)
            second = client.post("/api/v1/tokens", json={"description": "two"}, headers=headers)
            limited = client.post("/api/v1/tokens", json={"description": "three"}, headers=headers)
            first_id = first.json()["token_info"]["token_id"]
            disabled = client.patch(
                f"/api/v1/tokens/{first_id}/status",
                json={"enabled": False},
                headers=headers,
            )
            still_limited = client.post(
                "/api/v1/tokens",
                json={"description": "four"},
                headers=headers,
            )
            deleted = client.delete(f"/api/v1/tokens/{first_id}", headers=headers)
            after_delete = client.post(
                "/api/v1/tokens",
                json={"description": "five"},
                headers=headers,
            )
            invalid = client.patch(
                "/api/v1/system-config",
                json={"api_key_max_count": "-1"},
                headers=headers,
            )

        self.assertEqual(configured.status_code, 200)
        self.assertEqual(configured.json()["config"]["api_key_max_count"], "2")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(limited.status_code, 409)
        self.assertEqual(limited.json()["error"]["code"], "TOKEN_LIMIT_EXCEEDED")
        self.assertEqual(disabled.status_code, 200)
        self.assertEqual(still_limited.status_code, 409)
        self.assertEqual(still_limited.json()["error"]["code"], "TOKEN_LIMIT_EXCEEDED")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(after_delete.status_code, 200)
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json()["error"]["code"], "INVALID_INPUT")

    def test_existing_admin_receives_system_config_permission_after_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            auth = AuthService(database_path)
            original_platform = PlatformServices(database_path)
            admin_role = original_platform.permissions.repository.get_role("admin")
            assert admin_role is not None
            original_platform.permissions.repository.save_role(
                replace(
                    admin_role,
                    permissions=tuple(
                        permission
                        for permission in admin_role.permissions
                        if permission != "system:write"
                    ),
                )
            )
            original_platform.permissions.repository.settings.delete_settings(
                "permission_migrations",
                keys={"admin_system_config_permission_v1"},
            )

            upgraded_platform = PlatformServices(database_path)
            client = TestClient(
                create_app(
                    LocalQuestionIndex(()),
                    auth_service=auth,
                    platform_services=upgraded_platform,
                    require_auth=True,
                )
            )
            owner_headers = self._register_and_login(client, "upgrade-owner")
            client.post(
                "/api/v1/auth/register",
                json={"username": "upgrade-admin", "password": "password123"},
            )
            promoted = client.patch(
                "/api/v1/users/upgrade-admin",
                json={"role": "admin"},
                headers=owner_headers,
            )
            admin_login = client.post(
                "/api/v1/auth/login",
                json={"username": "upgrade-admin", "password": "password123"},
            )
            admin_headers = {"Authorization": f"Bearer {admin_login.json()['token']}"}
            configured = client.patch(
                "/api/v1/system-config",
                json={"api_key_max_count": "5"},
                headers=admin_headers,
            )

        self.assertEqual(promoted.status_code, 200)
        self.assertEqual(configured.status_code, 200, configured.text)
        self.assertEqual(configured.json()["config"]["api_key_max_count"], "5")

    def test_deleted_key_invalidates_existing_capability_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client, _auth, _platform = self._client(directory)
            headers = self._register_and_login(client, "owner")
            created = client.post(
                "/api/v1/tokens",
                json={"description": "delete-share"},
                headers=headers,
            )
            token_id = created.json()["token_info"]["token_id"]
            deleted = client.delete(f"/api/v1/tokens/{token_id}", headers=headers)
            copied = client.post(
                f"/api/v1/tokens/{token_id}/copy-value",
                headers=headers,
            )
            shared = client.post(
                f"/api/v1/tokens/{token_id}/share-link",
                headers=headers,
            )

        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(copied.status_code, 404)
        self.assertEqual(copied.json()["error"]["code"], "TOKEN_NOT_FOUND")
        self.assertEqual(shared.status_code, 404)
        self.assertEqual(shared.json()["error"]["code"], "TOKEN_NOT_FOUND")

    def test_legacy_key_without_raw_value_still_authenticates_but_cannot_be_shared(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client, _auth, platform = self._client(directory)
            headers = self._register_and_login(client, "owner")
            created = client.post(
                "/api/v1/tokens",
                json={"description": "legacy"},
                headers=headers,
            )
            raw_token = created.json()["token"]
            token_id = created.json()["token_info"]["token_id"]
            record = platform.tokens.repository.get_token(token_id)
            assert record is not None
            record.token_raw = ""
            platform.tokens.repository.save_token(record)

            copied = client.post(
                f"/api/v1/tokens/{token_id}/copy-value",
                headers=headers,
            )
            shared = client.post(
                f"/api/v1/tokens/{token_id}/share-link",
                headers=headers,
            )
            imported = client.get(
                "/api/v1/tokens/ocs-config",
                params={"token_id": token_id},
                headers=headers,
            )

            # key_hash remains the authentication index after token_raw is unavailable.
            authenticated = client.get(
                "/ocs/query",
                params={"title": "legacy key", "type": "single"},
                headers={"Authorization": f"Bearer {raw_token}"},
            )

        self.assertEqual(copied.status_code, 409)
        self.assertEqual(copied.json()["error"]["code"], "TOKEN_VALUE_UNAVAILABLE")
        self.assertEqual(shared.status_code, 409)
        self.assertEqual(shared.json()["error"]["code"], "TOKEN_VALUE_UNAVAILABLE")
        self.assertEqual(imported.status_code, 200)
        self.assertTrue(imported.json()["requires_token_replacement"])
        self.assertFalse(imported.json()["token_option"]["is_recoverable"])
        self.assertNotIn("script", imported.json())
        self.assertEqual(
            imported.json()["ocs_config"][0]["headers"]["Authorization"],
            "Bearer {{TOKEN}}",
        )
        self.assertEqual(authenticated.status_code, 200)

    def test_database_has_token_raw_compatibility_column_but_no_share_table(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = self._runtime_database_path(directory)
            engine = get_engine(database_path)
            table_names = set(inspect(engine).get_table_names())
            with engine.connect() as connection:
                token_columns = {
                    row[1]
                    for row in connection.execute(text("PRAGMA table_info(api_tokens)")).fetchall()
                }
            engine.dispose()

        self.assertIn("api_tokens", table_names)
        self.assertIn("token_raw", token_columns)
        self.assertNotIn("token_shares", table_names)

    def test_old_sqlite_api_tokens_table_gets_token_raw_column(self) -> None:
        engine = create_engine("sqlite:///:memory:", future=True)
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE api_tokens (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        token_id VARCHAR(64) UNIQUE,
                        user_id VARCHAR(64),
                        key_hash VARCHAR(128) UNIQUE,
                        key_mask VARCHAR(64),
                        description VARCHAR(255),
                        status VARCHAR(32),
                        created_at FLOAT,
                        last_used_at FLOAT,
                        usage_count INTEGER DEFAULT 0
                    )
                    """
                )
            )

        database_module.ensure_sqlite_compat_columns(engine)
        with engine.connect() as connection:
            columns = {
                row[1]
                for row in connection.execute(text("PRAGMA table_info(api_tokens)")).fetchall()
            }
        engine.dispose()

        self.assertIn("token_raw", columns)
        self.assertIn("bind_client", columns)
        self.assertIn("bound_client_id", columns)

    def test_runtime_log_redaction_never_keeps_token_value(self) -> None:
        raw_token = "sk_stqb_test_only_value"
        redacted = redact(
            {
                "token_raw": raw_token,
                "authorization": f"Bearer {raw_token}",
                "share_url": f"https://example.test/share/apikey#key={raw_token}",
            }
        )

        self.assertNotIn(raw_token, str(redacted))
        self.assertEqual(redacted["token_raw"], "[redacted]")
        self.assertEqual(redacted["authorization"], "[redacted]")
        self.assertEqual(redacted["share_url"], "[redacted]")


if __name__ == "__main__":
    unittest.main()
