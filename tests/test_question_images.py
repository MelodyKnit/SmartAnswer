"""题目图片本地存储与图床路由测试。"""

from __future__ import annotations

import base64
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.api.local_server import create_app  # noqa: E402
from study_qb_assistant.config import get_global_config  # noqa: E402
from study_qb_assistant.image_ocr import is_public_http_url  # noqa: E402
from study_qb_assistant.media.question_context import ImageAsset  # noqa: E402
from study_qb_assistant.media.question_images import hydrate_query_images_for_model  # noqa: E402
from study_qb_assistant.models import QuestionQuery  # noqa: E402
from study_qb_assistant.search import LocalQuestionIndex  # noqa: E402


class QuestionImageTests(unittest.TestCase):
    """验证 OCS 题目图片本地图床化链路。"""

    def test_data_url_image_is_stored_by_sha256_and_reused(self) -> None:
        """data URL 图片应按内容 SHA-256 存储，并复用同一文件。"""

        image_bytes = b"\x89PNG\r\n\x1a\nunit-test"
        data_url = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
        digest = hashlib.sha256(image_bytes).hexdigest()
        expected_filename = f"{digest}.png"

        with isolated_data_dir() as _directory:
            query = QuestionQuery(
                title="图片题",
                image_data_urls=(data_url,),
                question_type="single",
                service_base_url="https://ocs.example.com",
            )
            first = hydrate_query_images_for_model(query)
            second = hydrate_query_images_for_model(query)
            stored_files = list(get_global_config().ocs_images_dir.glob("*.png"))

        self.assertEqual(
            first.image_urls,
            (f"https://ocs.example.com/media/ocs/images/{expected_filename}",),
        )
        self.assertEqual(second.image_urls, first.image_urls)
        self.assertEqual(first.image_data_urls, ())
        self.assertEqual([path.name for path in stored_files], [expected_filename])

    def test_missing_public_base_url_falls_back_to_data_url(self) -> None:
        """无法生成公开图床地址时，应保留 data URL 兜底给本地开发使用。"""

        image_bytes = b"\x89PNG\r\n\x1a\nfallback"
        data_url = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")

        with isolated_data_dir(clear_public_base=True):
            query = QuestionQuery(
                title="图片题", image_data_urls=(data_url,), question_type="single"
            )
            hydrated = hydrate_query_images_for_model(query)

        self.assertEqual(hydrated.image_urls, query.image_urls)
        self.assertEqual(hydrated.image_data_urls, (data_url,))

    def test_mixed_data_and_option_url_images_are_hydrated_together(self) -> None:
        """题干 data URL 与选项图片 URL 同时存在时不应二选一丢图。"""

        stem_bytes = b"\x89PNG\r\n\x1a\nstem"
        option_bytes = b"\x89PNG\r\n\x1a\noption"
        stem_data_url = "data:image/png;base64," + base64.b64encode(stem_bytes).decode("ascii")
        option_data_url = "data:image/png;base64," + base64.b64encode(option_bytes).decode("ascii")
        option_url = "https://cdn.example.com/option-a.png"
        expected_urls = (
            f"https://ocs.example.com/media/ocs/images/{hashlib.sha256(stem_bytes).hexdigest()}.png",
            f"https://ocs.example.com/media/ocs/images/{hashlib.sha256(option_bytes).hexdigest()}.png",
        )

        def fake_fetch_public_image_asset(
            url: str, *, referer: str | None = None, request_id: str | None = None
        ) -> ImageAsset | None:
            if url != option_url:
                return None
            return ImageAsset(
                source_url=url,
                mime_type="image/png",
                content_bytes=option_bytes,
                data_url=option_data_url,
            )

        with isolated_data_dir() as _directory:
            query = QuestionQuery(
                title="图片题",
                image_data_urls=(stem_data_url,),
                option_image_urls={"A": option_url},
                question_type="single",
                service_base_url="https://ocs.example.com",
            )
            with patch(
                "study_qb_assistant.media.question_context.fetch_public_image_asset",
                side_effect=fake_fetch_public_image_asset,
            ):
                hydrated = hydrate_query_images_for_model(query)

        self.assertEqual(hydrated.image_urls, expected_urls)
        self.assertEqual(hydrated.image_data_urls, ())
        self.assertEqual(hydrated.option_image_urls, {})

    def test_media_route_serves_only_safe_ocs_image_files(self) -> None:
        """公开媒体路由只应返回受控文件名的题目图片。"""

        image_bytes = b"\x89PNG\r\n\x1a\nroute"
        digest = hashlib.sha256(image_bytes).hexdigest()
        filename = f"{digest}.png"

        with isolated_data_dir() as _directory:
            image_dir = get_global_config().ocs_images_dir
            image_dir.mkdir(parents=True, exist_ok=True)
            (image_dir / filename).write_bytes(image_bytes)
            client = TestClient(create_app(LocalQuestionIndex(()), require_auth=False))
            found = client.get(f"/media/ocs/images/{filename}")
            missing = client.get("/media/ocs/images/not-a-hash.png")

        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.content, image_bytes)
        self.assertEqual(missing.status_code, 404)

    def test_private_image_urls_are_rejected_before_fetching(self) -> None:
        """私网和回环图片 URL 应被拒绝，防止 SSRF。"""

        self.assertFalse(is_public_http_url("http://127.0.0.1/a.png"))
        self.assertFalse(is_public_http_url("http://10.0.0.1/a.png"))
        self.assertFalse(is_public_http_url("file:///tmp/a.png"))


class isolated_data_dir:
    """临时切换 `STQB_DATA_DIR`，避免测试污染真实 data 目录。"""

    def __init__(self, *, clear_public_base: bool = False) -> None:
        self.clear_public_base = clear_public_base
        self.tempdir = tempfile.TemporaryDirectory()
        self.previous_data_dir = os.environ.get("STQB_DATA_DIR")
        self.previous_public_base = os.environ.get("STQB_PUBLIC_BASE_URL")

    def __enter__(self) -> str:
        os.environ["STQB_DATA_DIR"] = self.tempdir.name
        if self.clear_public_base:
            os.environ.pop("STQB_PUBLIC_BASE_URL", None)
        return self.tempdir.name

    def __exit__(self, *_exc: object) -> None:
        if self.previous_data_dir is None:
            os.environ.pop("STQB_DATA_DIR", None)
        else:
            os.environ["STQB_DATA_DIR"] = self.previous_data_dir
        if self.previous_public_base is None:
            os.environ.pop("STQB_PUBLIC_BASE_URL", None)
        else:
            os.environ["STQB_PUBLIC_BASE_URL"] = self.previous_public_base
        self.tempdir.cleanup()


if __name__ == "__main__":
    unittest.main()
