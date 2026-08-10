"""错误处理改进的回归测试。

覆盖两个曾经的缺陷：
1. 全局异常处理器返回结构化的 500（含 type/detail），且带 CORS 头，
   否则浏览器跨域时会拦截整个响应，前端读不到错误信息。
2. image-generation-capabilities / infer-size 端点会把 service 抛出的
   ImageGenerationError 翻译成领域错误格式，而不是让它冒泡成笼统 500。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.api.exception_handlers import install_exception_handlers  # noqa: E402
from study_qb_assistant.api.middleware import install_http_middleware  # noqa: E402
from study_qb_assistant.api.v1.image_generation import router as ig_router  # noqa: E402
from study_qb_assistant.api.dependencies import get_image_generation_service  # noqa: E402
from study_qb_assistant.platform.image_generation.service import (  # noqa: E402
    ImageGenerationError,
)


class GlobalExceptionHandlerTests(unittest.TestCase):
    """验证全局异常处理器的结构化响应与 CORS 头。"""

    def _client(self) -> TestClient:
        app = FastAPI()
        install_exception_handlers(app)
        install_http_middleware(app)

        @app.get("/boom")
        async def boom():  # noqa: ANN202
            raise ValueError("模拟内部错误：数据库连接失败")

        return TestClient(app, raise_server_exceptions=False)

    def test_unhandled_exception_returns_structured_500(self) -> None:
        response = self._client().get("/boom")
        self.assertEqual(response.status_code, 500)
        body = response.json()
        self.assertFalse(body["ok"])
        error = body["error"]
        self.assertEqual(error["code"], "INTERNAL_SERVER_ERROR")
        self.assertEqual(error["type"], "ValueError")
        self.assertIn("数据库连接失败", error["detail"])

    def test_500_response_carries_cors_headers(self) -> None:
        response = self._client().get(
            "/boom", headers={"Origin": "http://localhost:5175"}
        )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.headers.get("access-control-allow-origin"),
            "http://localhost:5175",
        )


class _FakeCapabilitiesService:
    """get_capabilities 抛出领域错误的假 service。"""

    def get_capabilities(self, *, user_points: int):  # noqa: ANN001
        raise ImageGenerationError(
            "CAPABILITIES_RETRIEVAL_FAILED",
            "获取生图能力信息失败: RuntimeError: 数据库锁定",
            http_status=500,
        )


class ImageGenerationErrorTranslationTests(unittest.TestCase):
    """验证生图端点把领域错误翻译成结构化响应，而非笼统 500。"""

    def setUp(self) -> None:
        self._orig_current_user = ig_router.current_user
        self._orig_require_permissions = ig_router.require_permissions
        ig_router.current_user = lambda request: {
            "user_id": "u1",
            "username": "tester",
            "points": 100,
        }
        ig_router.require_permissions = lambda request, perms: None

    def tearDown(self) -> None:
        ig_router.current_user = self._orig_current_user
        ig_router.require_permissions = self._orig_require_permissions

    def _client(self) -> TestClient:
        app = FastAPI()
        install_exception_handlers(app)
        app.include_router(ig_router.build_image_generation_router())
        app.dependency_overrides[get_image_generation_service] = (
            lambda: _FakeCapabilitiesService()
        )
        return TestClient(app, raise_server_exceptions=False)

    def test_capabilities_translates_domain_error(self) -> None:
        response = self._client().get("/image-generation-capabilities")
        self.assertEqual(response.status_code, 500)
        error = response.json()["error"]
        # 关键：领域错误码，而不是被全局 handler 兜底成 INTERNAL_SERVER_ERROR
        self.assertEqual(error["code"], "CAPABILITIES_RETRIEVAL_FAILED")
        self.assertIn("数据库锁定", error["message"])


if __name__ == "__main__":
    unittest.main()
