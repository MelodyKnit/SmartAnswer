"""文本生图任务的 API、积分与私有资产闭环测试。"""

from __future__ import annotations

import io
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from study_qb_assistant.api.app import create_app
from study_qb_assistant.auth import AuthService
from study_qb_assistant.llm.image_generation import (
    GeneratedImage,
    ImageGenerationProviderError,
)
from study_qb_assistant.platform.container import PlatformServices
from study_qb_assistant.search import LocalQuestionIndex


def png_bytes() -> bytes:
    """构造一个通过生产图片校验的小型 PNG。"""

    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color=(36, 127, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


class SuccessfulImageProvider:
    """不触达网络的成功生图提供商替身。"""

    provider_name = "test-image-provider"

    def generate(self, _request) -> GeneratedImage:
        """返回可被私有资产层存储的标准 PNG。"""

        return GeneratedImage(
            content=png_bytes(),
            mime_type="image/png",
            width=8,
            height=8,
            provider_request_id="provider-success-1",
        )


class FailingImageProvider:
    """模拟供应商超时，验证失败任务自动退款。"""

    provider_name = "test-image-provider"

    def generate(self, _request) -> GeneratedImage:
        """返回可安全暴露的提供商错误分类。"""

        raise ImageGenerationProviderError("PROVIDER_TIMEOUT", "生图服务响应超时")


class RejectedImageProvider:
    """模拟供应商内容策略拒绝。"""

    provider_name = "test-image-provider"

    def generate(self, _request) -> GeneratedImage:
        """拒绝请求，不产生图片。"""

        raise ImageGenerationProviderError(
            "CONTENT_POLICY_REJECTED", "图片描述不符合生图服务的内容规范"
        )


class InvalidImageProvider:
    """模拟供应商返回无法通过图片解码校验的内容。"""

    provider_name = "test-image-provider"

    def generate(self, _request) -> GeneratedImage:
        """返回伪造字节，让资产层验证失败。"""

        return GeneratedImage(
            content=b"not-a-valid-image",
            mime_type="image/png",
            width=0,
            height=0,
        )


class ImageGenerationApiTests(unittest.TestCase):
    """覆盖生图模型、队列任务、积分结算和资源隔离。"""

    def build_client(self, directory: str) -> tuple[TestClient, AuthService, PlatformServices, dict[str, str]]:
        """创建独立数据库、首个管理员会话及生图策略。"""

        database_path = Path(directory) / "image-generation.sqlite3"
        auth = AuthService(database_path)
        platform = PlatformServices(database_path)
        platform.settings.set_system_config(
            {
                "default_user_points": "20",
                "image_generation_points": "7",
                "image_generation_max_active_jobs": "1",
                "image_generation_daily_limit": "5",
                "image_generation_retention_days": "30",
            }
        )
        client = TestClient(
            create_app(
                LocalQuestionIndex(()),
                auth_service=auth,
                platform_services=platform,
                require_auth=True,
            )
        )
        registered = client.post(
            "/api/v1/auth/register",
            json={"username": "owner", "password": "password123"},
        )
        self.assertEqual(registered.status_code, 200)
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "owner", "password": "password123"},
        )
        self.assertEqual(login.status_code, 200)
        return client, auth, platform, {"Authorization": f"Bearer {login.json()['token']}"}

    @staticmethod
    def create_active_model(client: TestClient, headers: dict[str, str]) -> dict:
        """通过管理员 API 创建一条独立且启用的生图模型。"""

        response = client.post(
            "/api/v1/image-generation-models",
            headers=headers,
            json={
                "name": "测试生图模型",
                "provider": "openai-images",
                "base_url": "https://images.example.test/v1",
                "model": "test-image-model",
                "api_key": "test-secret-key",
                "status": "active",
                "capabilities": ["text-to-image", "1024x1024"],
            },
        )
        assert response.status_code == 201, response.text
        return response.json()["model"]

    def test_successful_job_is_idempotent_and_private(self) -> None:
        """成功任务只扣一次积分，资产只能由所有者或管理员读取。"""

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"STQB_DATA_DIR": directory}, clear=False
        ):
            client, auth, platform, headers = self.build_client(directory)
            model = self.create_active_model(client, headers)
            self.assertNotIn("api_key", model)
            self.assertTrue(model["api_key_configured"])
            platform.image_generation.provider_factory = lambda _model: SuccessfulImageProvider()

            initial_points = auth.get_user("owner")["points"]
            created = client.post(
                "/api/v1/image-generations",
                headers=headers,
                json={
                    "prompt": "蓝色几何方块，白色背景",
                    "size": "1024x1024",
                    "idempotency_key": "job-success-1",
                },
            )
            self.assertEqual(created.status_code, 202)
            job_id = created.json()["job"]["job_id"]
            self.assertEqual(auth.get_user("owner")["points"], initial_points - 7)

            replay = client.post(
                "/api/v1/image-generations",
                headers=headers,
                json={
                    "prompt": "蓝色几何方块，白色背景",
                    "size": "1024x1024",
                    "idempotency_key": "job-success-1",
                },
            )
            self.assertEqual(replay.status_code, 200)
            self.assertTrue(replay.json()["idempotent_replay"])
            self.assertEqual(replay.json()["job"]["job_id"], job_id)
            self.assertEqual(auth.get_user("owner")["points"], initial_points - 7)

            limited = client.post(
                "/api/v1/image-generations",
                headers=headers,
                json={"prompt": "另一张图片", "idempotency_key": "job-concurrent-2"},
            )
            self.assertEqual(limited.status_code, 429)
            self.assertEqual(
                limited.json()["error"]["code"], "IMAGE_GENERATION_CONCURRENCY_LIMIT"
            )

            self.assertTrue(platform.image_generation.process_next_job())
            detail = client.get(f"/api/v1/image-generations/{job_id}", headers=headers)
            self.assertEqual(detail.status_code, 200)
            job = detail.json()["job"]
            self.assertEqual(job["status"], "succeeded")
            self.assertEqual(len(job["assets"]), 1)
            self.assertEqual(auth.get_user("owner")["points"], initial_points - 7)

            asset_id = job["assets"][0]["asset_id"]
            content = client.get(
                f"/api/v1/image-generations/{job_id}/assets/{asset_id}/content",
                headers=headers,
            )
            self.assertEqual(content.status_code, 200)
            self.assertEqual(content.headers["cache-control"], "private, no-store")
            self.assertTrue(content.content.startswith(b"\x89PNG"))

            client.post(
                "/api/v1/auth/register",
                json={"username": "other", "password": "password123"},
            )
            other_login = client.post(
                "/api/v1/auth/login",
                json={"username": "other", "password": "password123"},
            )
            other_headers = {"Authorization": f"Bearer {other_login.json()['token']}"}
            forbidden = client.get(
                f"/api/v1/image-generations/{job_id}/assets/{asset_id}/content",
                headers=other_headers,
            )
            self.assertEqual(forbidden.status_code, 403)

    def test_failed_job_refunds_points_and_trace_is_sanitized(self) -> None:
        """供应商异常必须失败退款，追溯仅保留稳定错误分类。"""

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"STQB_DATA_DIR": directory}, clear=False
        ):
            client, auth, platform, headers = self.build_client(directory)
            self.create_active_model(client, headers)
            platform.image_generation.provider_factory = lambda _model: FailingImageProvider()
            initial_points = auth.get_user("owner")["points"]

            created = client.post(
                "/api/v1/image-generations",
                headers=headers,
                json={"prompt": "供应商失败时需要退款", "idempotency_key": "job-failure-1"},
            )
            self.assertEqual(created.status_code, 202)
            job_id = created.json()["job"]["job_id"]
            self.assertEqual(auth.get_user("owner")["points"], initial_points - 7)

            self.assertTrue(platform.image_generation.process_next_job())
            detail = client.get(f"/api/v1/image-generations/{job_id}", headers=headers)
            self.assertEqual(detail.json()["job"]["status"], "failed")
            self.assertEqual(detail.json()["job"]["error_code"], "PROVIDER_TIMEOUT")
            self.assertEqual(auth.get_user("owner")["points"], initial_points)

            traces = client.get(
                "/api/v1/image-generation-traces",
                headers=headers,
                params={"job_id": job_id},
            )
            self.assertEqual(traces.status_code, 200)
            trace = traces.json()["traces"][0]
            self.assertFalse(trace["ok"])
            self.assertEqual(trace["error_code"], "PROVIDER_TIMEOUT")
            self.assertEqual(trace["error"], "生图任务执行失败")
            self.assertNotIn("供应商失败", trace["error"])

    def test_model_requires_key_and_queued_job_uses_its_snapshot(self) -> None:
        """模型凭据不能为空，后续改配置不应让已排队任务悄然切换模型参数。"""

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"STQB_DATA_DIR": directory}, clear=False
        ):
            client, _auth, platform, headers = self.build_client(directory)
            missing_key = client.post(
                "/api/v1/image-generation-models",
                headers=headers,
                json={
                    "name": "无凭据模型",
                    "provider": "openai-images",
                    "base_url": "https://images.example.test/v1",
                    "model": "test-image-model",
                },
            )
            self.assertEqual(missing_key.status_code, 400)
            self.assertEqual(missing_key.json()["error"]["code"], "INVALID_INPUT")

            model = self.create_active_model(client, headers)
            created = client.post(
                "/api/v1/image-generations",
                headers=headers,
                json={"prompt": "保留原模型快照", "idempotency_key": "job-snapshot-1"},
            )
            self.assertEqual(created.status_code, 202)
            job_id = created.json()["job"]["job_id"]

            # 新模型可用于后续提交；已提交任务仍应使用保存时的地址和模型标识。
            updated = client.patch(
                f"/api/v1/image-generation-models/{model['model_id']}",
                headers=headers,
                json={
                    "base_url": "https://changed.example.test/v1",
                    "model": "changed-image-model",
                    "status": "inactive",
                },
            )
            self.assertEqual(updated.status_code, 200)
            used_models = []

            def provider_factory(execution_model):
                used_models.append(execution_model)
                return SuccessfulImageProvider()

            platform.image_generation.provider_factory = provider_factory
            self.assertTrue(platform.image_generation.process_next_job())
            self.assertEqual(used_models[0].base_url, "https://images.example.test/v1")
            self.assertEqual(used_models[0].model, "test-image-model")
            detail = client.get(f"/api/v1/image-generations/{job_id}", headers=headers)
            self.assertEqual(detail.json()["job"]["status"], "succeeded")

    def test_recovery_refunds_interrupted_running_job_once(self) -> None:
        """应用重启恢复只结算遗留运行任务，重复执行不会重复退款。"""

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"STQB_DATA_DIR": directory}, clear=False
        ):
            client, auth, platform, headers = self.build_client(directory)
            self.create_active_model(client, headers)
            initial_points = auth.get_user("owner")["points"]
            created = client.post(
                "/api/v1/image-generations",
                headers=headers,
                json={"prompt": "模拟进程中断", "idempotency_key": "job-recovery-1"},
            )
            self.assertEqual(created.status_code, 202)
            job_id = created.json()["job"]["job_id"]
            self.assertEqual(auth.get_user("owner")["points"], initial_points - 7)
            claimed = platform.image_generation.repository.claim_next_job(time.time() - 600)
            self.assertIsNotNone(claimed)

            running_delete = client.delete(f"/api/v1/image-generations/{job_id}", headers=headers)
            self.assertEqual(running_delete.status_code, 409)
            self.assertEqual(running_delete.json()["error"]["code"], "JOB_RUNNING")
            self.assertEqual(auth.get_user("owner")["points"], initial_points - 7)

            self.assertEqual(platform.image_generation.recover_abandoned_jobs(max_running_seconds=60), 1)
            self.assertEqual(platform.image_generation.recover_abandoned_jobs(max_running_seconds=60), 0)
            detail = client.get(f"/api/v1/image-generations/{job_id}", headers=headers)
            self.assertEqual(detail.json()["job"]["status"], "failed")
            self.assertEqual(detail.json()["job"]["error_code"], "WORKER_INTERRUPTED")
            self.assertEqual(auth.get_user("owner")["points"], initial_points)

    def test_rejected_and_invalid_images_are_not_charged(self) -> None:
        """内容策略拒绝和非法图片都必须终态化并撤销预扣积分。"""

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"STQB_DATA_DIR": directory}, clear=False
        ):
            client, auth, platform, headers = self.build_client(directory)
            self.create_active_model(client, headers)
            initial_points = auth.get_user("owner")["points"]
            cases = [
                (RejectedImageProvider(), "rejected", "CONTENT_POLICY_REJECTED"),
                (InvalidImageProvider(), "failed", "INVALID_GENERATED_IMAGE"),
            ]
            for index, (provider, expected_status, expected_code) in enumerate(cases, start=1):
                platform.image_generation.provider_factory = lambda _model, provider=provider: provider
                created = client.post(
                    "/api/v1/image-generations",
                    headers=headers,
                    json={
                        "prompt": f"失败情形 {index}",
                        "idempotency_key": f"job-rejected-{index}",
                    },
                )
                self.assertEqual(created.status_code, 202)
                self.assertTrue(platform.image_generation.process_next_job())
                job = client.get(
                    f"/api/v1/image-generations/{created.json()['job']['job_id']}",
                    headers=headers,
                ).json()["job"]
                self.assertEqual(job["status"], expected_status)
                self.assertEqual(job["error_code"], expected_code)
                self.assertEqual(auth.get_user("owner")["points"], initial_points)

    def test_storage_failure_refunds_points(self) -> None:
        """图片字节有效但存储失败时，也不能留下已扣积分的悬挂任务。"""

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"STQB_DATA_DIR": directory}, clear=False
        ):
            client, auth, platform, headers = self.build_client(directory)
            self.create_active_model(client, headers)
            platform.image_generation.provider_factory = lambda _model: SuccessfulImageProvider()
            initial_points = auth.get_user("owner")["points"]
            created = client.post(
                "/api/v1/image-generations",
                headers=headers,
                json={"prompt": "模拟图片存储失败", "idempotency_key": "job-storage-failure"},
            )
            self.assertEqual(created.status_code, 202)

            with patch(
                "study_qb_assistant.platform.image_generation.service.store_generated_image",
                side_effect=OSError("disk unavailable"),
            ):
                self.assertTrue(platform.image_generation.process_next_job())

            job = client.get(
                f"/api/v1/image-generations/{created.json()['job']['job_id']}", headers=headers
            ).json()["job"]
            self.assertEqual(job["status"], "failed")
            self.assertEqual(job["error_code"], "IMAGE_GENERATION_FAILED")
            self.assertEqual(auth.get_user("owner")["points"], initial_points)

    def test_deleted_and_expired_assets_revoke_private_access(self) -> None:
        """用户删除或保留期清理后，数据库与磁盘资源都不应继续可访问。"""

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"STQB_DATA_DIR": directory}, clear=False
        ):
            client, _auth, platform, headers = self.build_client(directory)
            self.create_active_model(client, headers)
            platform.image_generation.provider_factory = lambda _model: SuccessfulImageProvider()

            deleted_job = client.post(
                "/api/v1/image-generations",
                headers=headers,
                json={"prompt": "用户主动删除", "idempotency_key": "job-user-delete"},
            ).json()["job"]
            self.assertTrue(platform.image_generation.process_next_job())
            deleted_detail = client.get(
                f"/api/v1/image-generations/{deleted_job['job_id']}", headers=headers
            ).json()["job"]
            deleted_asset_id = deleted_detail["assets"][0]["asset_id"]
            delete_response = client.delete(
                f"/api/v1/image-generations/{deleted_job['job_id']}", headers=headers
            )
            self.assertEqual(delete_response.status_code, 200)
            self.assertEqual(delete_response.json()["job"]["status"], "deleted")
            self.assertEqual(
                client.get(
                    f"/api/v1/image-generations/{deleted_job['job_id']}/assets/"
                    f"{deleted_asset_id}/content",
                    headers=headers,
                ).status_code,
                404,
            )

            expiring_job = client.post(
                "/api/v1/image-generations",
                headers=headers,
                json={"prompt": "保留期清理", "idempotency_key": "job-expiry-cleanup"},
            ).json()["job"]
            self.assertTrue(platform.image_generation.process_next_job())
            expiry = client.get(
                f"/api/v1/image-generations/{expiring_job['job_id']}", headers=headers
            ).json()["job"]["expires_at"]
            with patch(
                "study_qb_assistant.platform.image_generation.service.time.time",
                return_value=expiry + 1,
            ):
                self.assertEqual(platform.image_generation.cleanup_expired_assets(), 1)
            expired_detail = client.get(
                f"/api/v1/image-generations/{expiring_job['job_id']}", headers=headers
            ).json()["job"]
            self.assertEqual(expired_detail["status"], "deleted")
            self.assertEqual(expired_detail["assets"], [])

    def test_unavailable_model_and_insufficient_points_do_not_create_a_charge(self) -> None:
        """无模型或余额不足必须在预扣前明确失败。"""

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"STQB_DATA_DIR": directory}, clear=False
        ):
            client, auth, platform, headers = self.build_client(directory)
            initial_points = auth.get_user("owner")["points"]
            unavailable = client.post(
                "/api/v1/image-generations",
                headers=headers,
                json={"prompt": "没有模型", "idempotency_key": "job-no-model"},
            )
            self.assertEqual(unavailable.status_code, 503)
            self.assertEqual(auth.get_user("owner")["points"], initial_points)

            self.create_active_model(client, headers)
            platform.settings.set_system_config({"image_generation_points": "99"})
            insufficient = client.post(
                "/api/v1/image-generations",
                headers=headers,
                json={"prompt": "余额不足", "idempotency_key": "job-insufficient"},
            )
            self.assertEqual(insufficient.status_code, 400)
            self.assertEqual(insufficient.json()["error"]["code"], "INSUFFICIENT_POINTS")
            self.assertEqual(auth.get_user("owner")["points"], initial_points)

    def test_enabling_a_model_deactivates_the_previous_one(self) -> None:
        """首版只允许一个可选模型，避免用户请求被隐式分流。"""

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"STQB_DATA_DIR": directory}, clear=False
        ):
            client, _auth, _platform, headers = self.build_client(directory)
            first = self.create_active_model(client, headers)
            second = client.post(
                "/api/v1/image-generation-models",
                headers=headers,
                json={
                    "name": "备用生图模型",
                    "provider": "openai-images",
                    "base_url": "https://images-backup.example.test/v1",
                    "model": "backup-image-model",
                    "api_key": "backup-secret-key",
                    "status": "active",
                },
            )
            self.assertEqual(second.status_code, 201)
            models = client.get("/api/v1/image-generation-models", headers=headers).json()["models"]
            active_models = [item for item in models if item["status"] == "active"]
            self.assertEqual(len(active_models), 1)
            self.assertEqual(active_models[0]["model_id"], second.json()["model"]["model_id"])
            self.assertEqual(
                next(item for item in models if item["model_id"] == first["model_id"])["status"],
                "inactive",
            )


if __name__ == "__main__":
    unittest.main()
