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


def png_bytes(width: int = 8, height: int = 8) -> bytes:
    """构造一个通过生产图片校验的小型 PNG。"""

    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=(36, 127, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


class SuccessfulImageProvider:
    """不触达网络的成功生图提供商替身。"""

    provider_name = "test-image-provider"

    def generate(self, request) -> GeneratedImage:
        """返回可被私有资产层存储的标准 PNG。"""

        request.notify_provider_dispatch()
        return GeneratedImage(
            content=png_bytes(),
            mime_type="image/png",
            width=8,
            height=8,
            provider_request_id="provider-success-1",
        )


class CapturingImageProvider(SuccessfulImageProvider):
    """记录执行请求，用于验证任务快照不受后续配置修改影响。"""

    def __init__(self) -> None:
        self.requests = []

    def generate(self, request) -> GeneratedImage:
        self.requests.append(request)
        return super().generate(request)


class FailingImageProvider:
    """模拟供应商超时，验证失败任务自动退款。"""

    provider_name = "test-image-provider"

    def generate(self, request) -> GeneratedImage:
        """返回可安全暴露的提供商错误分类。"""

        request.notify_provider_dispatch()
        raise ImageGenerationProviderError("PROVIDER_TIMEOUT", "生图服务响应超时")


class RejectedImageProvider:
    """模拟供应商内容策略拒绝。"""

    provider_name = "test-image-provider"

    def generate(self, request) -> GeneratedImage:
        """拒绝请求，不产生图片。"""

        request.notify_provider_dispatch()
        raise ImageGenerationProviderError(
            "CONTENT_POLICY_REJECTED", "图片描述不符合生图服务的内容规范"
        )


class InvalidImageProvider:
    """模拟供应商返回无法通过图片解码校验的内容。"""

    provider_name = "test-image-provider"

    def generate(self, request) -> GeneratedImage:
        """返回伪造字节，让资产层验证失败。"""

        request.notify_provider_dispatch()
        return GeneratedImage(
            content=b"not-a-valid-image",
            mime_type="image/png",
            width=0,
            height=0,
        )


class PreDispatchFailureProvider:
    """模拟请求构造阶段失败，验证该阶段不会消耗积分。"""

    provider_name = "test-image-provider"

    def generate(self, _request) -> GeneratedImage:
        """在通知上游请求前抛出可预期的输入错误。"""

        raise ImageGenerationProviderError("INVALID_MASK_IMAGE", "蒙版图片无法用于编辑")


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

    def test_gemini_output_options_are_persisted_and_used_by_the_worker(self) -> None:
        """Gemini 画幅/像素档位应进入任务快照，而非由执行时模型配置覆盖。"""

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"STQB_DATA_DIR": directory}, clear=False
        ):
            client, _auth, platform, headers = self.build_client(directory)
            created_model = client.post(
                "/api/v1/image-generation-models",
                headers=headers,
                json={
                    "name": "Gemini 生图",
                    "provider": "gemini-native",
                    "base_url": "https://images.example.test/v1beta",
                    "model": "gemini-image-model",
                    "api_key": "test-secret-key",
                    "protocol_config": {
                        "auth_mode": "bearer",
                        "aspect_ratios": ["1:1", "16:9"],
                        "image_sizes": ["1K", "2K"],
                    },
                },
            )
            self.assertEqual(created_model.status_code, 201, created_model.text)
            model = created_model.json()["model"]
            self.assertEqual(model["protocol_config"]["auth_mode"], "bearer")

            capabilities = client.get(
                "/api/v1/image-generation-capabilities", headers=headers
            ).json()["capabilities"]
            self.assertEqual(capabilities["output"]["kind"], "gemini")
            self.assertEqual(capabilities["output"]["image_sizes"], ["1K", "2K"])

            created_job = client.post(
                "/api/v1/image-generations",
                headers=headers,
                json={
                    "prompt": "宽屏纸飞机插画",
                    "output": {"aspect_ratio": "16:9", "image_size": "2K"},
                    "idempotency_key": "gemini-output-options",
                },
            )
            self.assertEqual(created_job.status_code, 202, created_job.text)
            self.assertEqual(created_job.json()["job"]["size"], "16:9 · 2K")
            self.assertEqual(
                created_job.json()["job"]["output"],
                {"aspect_ratio": "16:9", "image_size": "2K"},
            )

            captured_provider = CapturingImageProvider()
            platform.image_generation.provider_factory = lambda _model: captured_provider
            self.assertTrue(platform.image_generation.process_next_job())
            self.assertEqual(
                captured_provider.requests[0].output_options,
                {"aspect_ratio": "16:9", "image_size": "2K"},
            )
            completed = client.get(
                f"/api/v1/image-generations/{created_job.json()['job']['job_id']}",
                headers=headers,
            ).json()["job"]
            self.assertEqual(completed["assets"][0]["width"], 8)
            self.assertEqual(completed["assets"][0]["height"], 8)

            mixed = client.post(
                "/api/v1/image-generations",
                headers=headers,
                json={
                    "prompt": "冲突尺寸参数",
                    "size": "1024x1024",
                    "output": {"aspect_ratio": "1:1", "image_size": "1K"},
                },
            )
            self.assertEqual(mixed.status_code, 400)
            self.assertEqual(mixed.json()["error"]["code"], "INVALID_INPUT")

    def test_failed_job_is_refunded_after_provider_timeout_and_trace_is_sanitized(self) -> None:
        """供应商超时后应退回预扣积分，追溯仅保留稳定错误分类。"""

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
                json={"prompt": "供应商失败仍需结算", "idempotency_key": "job-failure-1"},
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

    def test_rejected_and_invalid_images_refund_the_reservation(self) -> None:
        """内容拒绝与非法输出都不能保留未成功任务的积分扣费。"""

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

    def test_storage_failure_refunds_the_reservation(self) -> None:
        """供应商返回后本地落盘失败时，应退回预扣积分。"""

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

    def test_pre_dispatch_failure_refunds_points(self) -> None:
        """请求构造或本地校验失败时，应释放预扣积分且不产生供应商调用。"""

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"STQB_DATA_DIR": directory}, clear=False
        ):
            client, auth, platform, headers = self.build_client(directory)
            self.create_active_model(client, headers)
            platform.image_generation.provider_factory = lambda _model: PreDispatchFailureProvider()
            initial_points = auth.get_user("owner")["points"]
            created = client.post(
                "/api/v1/image-generations",
                headers=headers,
                json={"prompt": "发送前失败", "idempotency_key": "job-pre-dispatch-failure"},
            )
            self.assertEqual(created.status_code, 202)
            self.assertTrue(platform.image_generation.process_next_job())
            job = client.get(
                f"/api/v1/image-generations/{created.json()['job']['job_id']}", headers=headers
            ).json()["job"]
            self.assertEqual(job["error_code"], "INVALID_MASK_IMAGE")
            self.assertEqual(auth.get_user("owner")["points"], initial_points)

    def test_verified_edit_mode_uses_private_source_and_rejects_raw_content(self) -> None:
        """编辑任务只可引用私有资产，且必须先通过当前模型能力测试。"""

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"STQB_DATA_DIR": directory}, clear=False
        ):
            client, auth, platform, headers = self.build_client(directory)
            model = self.create_active_model(client, headers)
            provider = CapturingImageProvider()
            platform.image_generation.provider_factory = lambda _model: provider
            initial_points = auth.get_user("owner")["points"]

            uploaded = client.post(
                "/api/v1/image-generation-inputs",
                headers=headers,
                params={"kind": "source"},
                files={"image": ("source.png", png_bytes(), "image/png")},
            )
            self.assertEqual(uploaded.status_code, 201, uploaded.text)
            source_id = uploaded.json()["asset"]["input_id"]
            client.post(
                "/api/v1/auth/register",
                json={"username": "other", "password": "password123"},
            )
            other_login = client.post(
                "/api/v1/auth/login",
                json={"username": "other", "password": "password123"},
            )
            other_headers = {"Authorization": f"Bearer {other_login.json()['token']}"}
            self.assertEqual(
                client.get(
                    f"/api/v1/image-generation-inputs/{source_id}/content",
                    headers=other_headers,
                ).status_code,
                403,
            )
            reference = {
                "source_kind": "uploaded",
                "source_id": source_id,
                "role": "source",
            }

            unverified = client.post(
                "/api/v1/image-generations",
                headers=headers,
                json={
                    "prompt": "把蓝色方块改成红色圆形",
                    "mode": "image_edit",
                    "input_assets": [reference],
                },
            )
            self.assertEqual(unverified.status_code, 409)
            self.assertEqual(unverified.json()["error"]["code"], "IMAGE_EDIT_NOT_VERIFIED")
            self.assertEqual(auth.get_user("owner")["points"], initial_points)

            raw_content = client.post(
                "/api/v1/image-generations",
                headers=headers,
                json={
                    "prompt": "不允许传递原始图片内容",
                    "mode": "image_edit",
                    "input_assets": [{**reference, "data_url": "data:image/png;base64,AA=="}],
                },
            )
            self.assertEqual(raw_content.status_code, 422)

            verified = client.post(
                f"/api/v1/image-generation-models/{model['model_id']}/test",
                headers=headers,
                json={"operation": "whole_edit"},
            )
            self.assertEqual(verified.status_code, 200)
            self.assertTrue(verified.json()["ok"])
            capabilities = client.get(
                "/api/v1/image-generation-capabilities", headers=headers
            ).json()["capabilities"]
            self.assertIn("image_edit", capabilities["input"]["available_modes"])

            created = client.post(
                "/api/v1/image-generations",
                headers=headers,
                json={
                    "prompt": "把蓝色方块改成红色圆形",
                    "mode": "image_edit",
                    "input_assets": [reference],
                    "idempotency_key": "private-edit-source",
                },
            )
            self.assertEqual(created.status_code, 202, created.text)
            self.assertEqual(auth.get_user("owner")["points"], initial_points - 7)
            self.assertEqual(
                client.delete(
                    f"/api/v1/image-generation-inputs/{source_id}", headers=headers
                ).status_code,
                409,
            )
            self.assertTrue(platform.image_generation.process_next_job())
            execution_request = provider.requests[-1]
            self.assertEqual(execution_request.mode, "image_edit")
            self.assertEqual(len(execution_request.input_images), 1)
            self.assertEqual(execution_request.input_images[0].role, "source")
            self.assertIsNone(execution_request.mask_image)

    def test_mask_dimension_mismatch_refunds_before_provider_dispatch(self) -> None:
        """局部编辑的主图和蒙版尺寸不一致时，不应向供应商发送请求。"""

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"STQB_DATA_DIR": directory}, clear=False
        ):
            client, auth, platform, headers = self.build_client(directory)
            model = self.create_active_model(client, headers)
            provider = CapturingImageProvider()
            platform.image_generation.provider_factory = lambda _model: provider
            initial_points = auth.get_user("owner")["points"]

            source = client.post(
                "/api/v1/image-generation-inputs",
                headers=headers,
                params={"kind": "source"},
                files={"image": ("source.png", png_bytes(8, 8), "image/png")},
            ).json()["asset"]
            mask = client.post(
                "/api/v1/image-generation-inputs",
                headers=headers,
                params={"kind": "mask"},
                files={"image": ("mask.png", png_bytes(4, 4), "image/png")},
            ).json()["asset"]
            verified = client.post(
                f"/api/v1/image-generation-models/{model['model_id']}/test",
                headers=headers,
                json={"operation": "masked_edit"},
            )
            self.assertTrue(verified.json()["ok"])
            capability_test_call_count = len(provider.requests)

            created = client.post(
                "/api/v1/image-generations",
                headers=headers,
                json={
                    "prompt": "只修改白色区域",
                    "mode": "masked_edit",
                    "input_assets": [
                        {"source_kind": "uploaded", "source_id": source["input_id"], "role": "source"},
                        {"source_kind": "uploaded", "source_id": mask["input_id"], "role": "mask"},
                    ],
                    "idempotency_key": "mask-dimension-mismatch",
                },
            )
            self.assertEqual(created.status_code, 202, created.text)
            self.assertTrue(platform.image_generation.process_next_job())
            job = client.get(
                f"/api/v1/image-generations/{created.json()['job']['job_id']}", headers=headers
            ).json()["job"]
            self.assertEqual(job["error_code"], "INVALID_MASK_IMAGE")
            self.assertEqual(auth.get_user("owner")["points"], initial_points)
            self.assertEqual(len(provider.requests), capability_test_call_count)

    def test_masked_edit_rejects_source_asset_used_as_mask(self) -> None:
        """蒙版引用必须来自规范化蒙版资产，不能把普通参考图伪装成蒙版。"""

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"STQB_DATA_DIR": directory}, clear=False
        ):
            client, auth, platform, headers = self.build_client(directory)
            model = self.create_active_model(client, headers)
            platform.image_generation.provider_factory = lambda _model: CapturingImageProvider()
            initial_points = auth.get_user("owner")["points"]
            source = client.post(
                "/api/v1/image-generation-inputs",
                headers=headers,
                params={"kind": "source"},
                files={"image": ("source.png", png_bytes(), "image/png")},
            ).json()["asset"]
            verified = client.post(
                f"/api/v1/image-generation-models/{model['model_id']}/test",
                headers=headers,
                json={"operation": "masked_edit"},
            )
            self.assertTrue(verified.json()["ok"])

            created = client.post(
                "/api/v1/image-generations",
                headers=headers,
                json={
                    "prompt": "只修改白色区域",
                    "mode": "masked_edit",
                    "input_assets": [
                        {"source_kind": "uploaded", "source_id": source["input_id"], "role": "source"},
                        {"source_kind": "uploaded", "source_id": source["input_id"], "role": "mask"},
                    ],
                    "idempotency_key": "source-is-not-mask",
                },
            )

            self.assertEqual(created.status_code, 400, created.text)
            self.assertEqual(created.json()["error"]["code"], "INVALID_IMAGE_INPUT")
            self.assertEqual(auth.get_user("owner")["points"], initial_points)

    def test_generated_asset_can_be_reused_only_with_its_own_source_job(self) -> None:
        """历史生成结果可复用，但资产 ID 与来源任务 ID 必须同时匹配。"""

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"STQB_DATA_DIR": directory}, clear=False
        ):
            client, _auth, platform, headers = self.build_client(directory)
            model = self.create_active_model(client, headers)
            provider = CapturingImageProvider()
            platform.image_generation.provider_factory = lambda _model: provider
            verified = client.post(
                f"/api/v1/image-generation-models/{model['model_id']}/test",
                headers=headers,
                json={"operation": "whole_edit"},
            )
            self.assertTrue(verified.json()["ok"])

            base = client.post(
                "/api/v1/image-generations",
                headers=headers,
                json={"prompt": "蓝色方块", "idempotency_key": "history-base-image"},
            )
            self.assertEqual(base.status_code, 202)
            self.assertTrue(platform.image_generation.process_next_job())
            base_job = client.get(
                f"/api/v1/image-generations/{base.json()['job']['job_id']}", headers=headers
            ).json()["job"]
            source_asset_id = base_job["assets"][0]["asset_id"]

            mismatched = client.post(
                "/api/v1/image-generations",
                headers=headers,
                json={
                    "prompt": "把图形改成红色圆形",
                    "mode": "image_edit",
                    "input_assets": [
                        {
                            "source_kind": "generated",
                            "source_id": source_asset_id,
                            "source_job_id": "another-job",
                            "role": "source",
                        }
                    ],
                },
            )
            self.assertEqual(mismatched.status_code, 400)
            self.assertEqual(mismatched.json()["error"]["code"], "INVALID_IMAGE_INPUT")

            edited = client.post(
                "/api/v1/image-generations",
                headers=headers,
                json={
                    "prompt": "把图形改成红色圆形",
                    "mode": "image_edit",
                    "input_assets": [
                        {
                            "source_kind": "generated",
                            "source_id": source_asset_id,
                            "source_job_id": base_job["job_id"],
                            "role": "source",
                        }
                    ],
                    "idempotency_key": "history-image-edit",
                },
            )
            self.assertEqual(edited.status_code, 202, edited.text)
            self.assertTrue(platform.image_generation.process_next_job())
            execution_request = provider.requests[-1]
            self.assertEqual(execution_request.mode, "image_edit")
            self.assertEqual(len(execution_request.input_images), 1)
            self.assertEqual(execution_request.input_images[0].role, "source")

    def test_model_configuration_change_invalidates_verified_edit_modes(self) -> None:
        """编辑能力测试必须绑定当前模型配置，避免修改网关后继续误开放。"""

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"STQB_DATA_DIR": directory}, clear=False
        ):
            client, _auth, platform, headers = self.build_client(directory)
            model = self.create_active_model(client, headers)
            platform.image_generation.provider_factory = lambda _model: SuccessfulImageProvider()
            tested = client.post(
                f"/api/v1/image-generation-models/{model['model_id']}/test",
                headers=headers,
                json={"operation": "whole_edit"},
            )
            self.assertTrue(tested.json()["ok"])
            before_update = client.get(
                "/api/v1/image-generation-capabilities", headers=headers
            ).json()["capabilities"]
            self.assertIn("image_edit", before_update["input"]["available_modes"])

            updated = client.patch(
                f"/api/v1/image-generation-models/{model['model_id']}",
                headers=headers,
                json={"timeout_seconds": 61},
            )
            self.assertEqual(updated.status_code, 200)
            after_update = client.get(
                "/api/v1/image-generation-capabilities", headers=headers
            ).json()["capabilities"]
            self.assertNotIn("image_edit", after_update["input"]["available_modes"])

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
