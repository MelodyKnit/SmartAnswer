"""三种正式生图协议的配置与输出参数回归测试。"""

from __future__ import annotations

import unittest

from sqlalchemy import create_engine, inspect, text

from study_qb_assistant.platform.image_generation.protocols import (
    GEMINI_NATIVE_PROVIDER,
    LEGACY_OPENAI_CHAT_IMAGE_PROVIDER,
    OPENAI_COMPATIBLE_IMAGES_PROVIDER,
    OPENAI_IMAGES_PROVIDER,
    ImageGenerationProtocolError,
    normalize_input_capabilities,
    normalize_output_options,
    normalize_protocol_config,
    public_output_capabilities,
)
from study_qb_assistant.storage.database import ensure_sqlite_compat_columns


class ImageGenerationProtocolTests(unittest.TestCase):
    """协议配置必须决定能力边界，不能把任意参数透传到上游。"""

    def test_gemini_native_exposes_declared_aspect_ratio_and_pixel_tier(self) -> None:
        """Gemini 的画幅与像素档位应按模型配置归一化。"""

        config = normalize_protocol_config(
            GEMINI_NATIVE_PROVIDER,
            {
                "auth_mode": "bearer",
                "aspect_ratios": ["1:1", "16:9"],
                "image_sizes": ["1k", "2K"],
            },
        )
        label, output = normalize_output_options(
            GEMINI_NATIVE_PROVIDER,
            config,
            output={"aspect_ratio": "16:9", "image_size": "2k"},
        )

        self.assertEqual(label, "16:9 · 2K")
        self.assertEqual(output, {"aspect_ratio": "16:9", "image_size": "2K"})
        self.assertEqual(config["auth_mode"], "bearer")
        self.assertEqual(
            public_output_capabilities(GEMINI_NATIVE_PROVIDER, config)["kind"],
            "gemini",
        )

    def test_openai_images_custom_size_requires_explicit_constraints(self) -> None:
        """OpenAI 原生协议只在管理员开启后接受合规自定义尺寸。"""

        config = normalize_protocol_config(
            OPENAI_IMAGES_PROVIDER,
            {
                "preset_sizes": ["1024x1024"],
                "allow_custom_size": True,
                "custom_size_constraints": {
                    "min_width": 512,
                    "max_width": 4096,
                    "min_height": 512,
                    "max_height": 4096,
                    "step": 16,
                    "min_pixels": 655360,
                    "max_pixels": 10000000,
                },
            },
        )
        _, output = normalize_output_options(
            OPENAI_IMAGES_PROVIDER,
            config,
            output={"size": "2048x1152"},
        )
        self.assertEqual(output, {"size": "2048x1152"})

        with self.assertRaises(ImageGenerationProtocolError):
            normalize_output_options(
                OPENAI_IMAGES_PROVIDER,
                config,
                output={"size": "2051x1152"},
            )

    def test_compatible_images_rejects_custom_size_and_mixed_legacy_input(self) -> None:
        """通用兼容协议只能使用声明的预设，旧新输入不能混用。"""

        config = normalize_protocol_config(
            OPENAI_COMPATIBLE_IMAGES_PROVIDER,
            {"preset_sizes": ["1024x1024", "1536x1024"]},
        )
        _, output = normalize_output_options(
            OPENAI_COMPATIBLE_IMAGES_PROVIDER,
            config,
            size="1536x1024",
        )
        self.assertEqual(output, {"size": "1536x1024"})

        with self.assertRaises(ImageGenerationProtocolError):
            normalize_output_options(
                OPENAI_COMPATIBLE_IMAGES_PROVIDER,
                config,
                output={"size": "2048x1152"},
            )
        with self.assertRaises(ImageGenerationProtocolError):
            normalize_output_options(
                OPENAI_COMPATIBLE_IMAGES_PROVIDER,
                config,
                size="1024x1024",
                output={"size": "1024x1024"},
            )

    def test_legacy_chat_protocol_keeps_model_controlled_output(self) -> None:
        """旧聊天生图配置仍可调用，但不将旧尺寸字段伪装成可控制能力。"""

        config = normalize_protocol_config(
            LEGACY_OPENAI_CHAT_IMAGE_PROVIDER,
            {},
            legacy_capabilities="text-to-image,1024x1024",
        )
        label, output = normalize_output_options(
            LEGACY_OPENAI_CHAT_IMAGE_PROVIDER,
            config,
            size="1024x1024",
        )

        self.assertEqual(label, "model-controlled")
        self.assertEqual(output, {"mode": "model-controlled"})

    def test_single_input_limit_disables_operations_that_need_two_images(self) -> None:
        """模型输入上限不足两张时，不得开放蒙版或多图参考能力。"""

        capabilities = normalize_input_capabilities(
            OPENAI_IMAGES_PROVIDER,
            {
                "whole_edit": True,
                "masked_edit": True,
                "multi_reference": True,
                "max_input_images": 1,
            },
        )

        self.assertTrue(capabilities["whole_edit"])
        self.assertFalse(capabilities["masked_edit"])
        self.assertFalse(capabilities["multi_reference"])

    def test_existing_sqlite_tables_gain_protocol_and_output_columns(self) -> None:
        """旧运行库启动后必须补齐字段，避免发布后任务接口读取失败。"""

        engine = create_engine("sqlite://")
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                    CREATE TABLE image_generation_models (
                        id INTEGER PRIMARY KEY,
                        model_id TEXT,
                        name TEXT,
                        provider TEXT,
                        base_url TEXT,
                        model TEXT,
                        api_key TEXT,
                        timeout_seconds REAL,
                        status TEXT,
                        capabilities TEXT,
                        created_at REAL,
                        updated_at REAL
                    )
                    """
                    )
                )
                connection.execute(
                    text(
                        """
                    CREATE TABLE image_generation_jobs (
                        id INTEGER PRIMARY KEY,
                        job_id TEXT,
                        user_id TEXT,
                        username TEXT,
                        prompt TEXT,
                        size TEXT,
                        model_id TEXT,
                        model_name TEXT,
                        model_snapshot TEXT,
                        status TEXT,
                        points_cost INTEGER,
                        reservation_order_id TEXT,
                        idempotency_key TEXT,
                        error_code TEXT,
                        error_message TEXT,
                        created_at REAL,
                        started_at REAL,
                        completed_at REAL,
                        updated_at REAL,
                        expires_at REAL
                    )
                    """
                    )
                )
            ensure_sqlite_compat_columns(engine)
            inspector = inspect(engine)
            model_columns = {
                column["name"] for column in inspector.get_columns("image_generation_models")
            }
            job_columns = {
                column["name"] for column in inspector.get_columns("image_generation_jobs")
            }
        finally:
            engine.dispose()

        self.assertIn("protocol_config", model_columns)
        self.assertIn("output_options", job_columns)


if __name__ == "__main__":
    unittest.main()
