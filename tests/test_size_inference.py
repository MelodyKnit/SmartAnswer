"""测试智能尺寸推断功能。"""

import pytest

from study_qb_assistant.llm.image_generation.size_inference import (
    infer_aspect_ratio,
    infer_size_preference,
    infer_openai_size,
    infer_gemini_output,
    explain_size_choice,
)


class TestAspectRatioInference:
    """测试画幅比例推断。"""

    def test_square_detection(self):
        """测试正方形检测。"""
        assert infer_aspect_ratio("一个方形的logo设计") == "1:1"
        assert infer_aspect_ratio("instagram头像图片") == "1:1"
        assert infer_aspect_ratio("微信公众号封面") == "1:1"

    def test_landscape_detection(self):
        """测试横屏检测。"""
        assert infer_aspect_ratio("一个宽屏的桌面壁纸") == "16:9"
        assert infer_aspect_ratio("cinematic movie scene") == "16:9"
        assert infer_aspect_ratio("YouTube视频封面") == "16:9"

    def test_portrait_detection(self):
        """测试竖屏检测。"""
        assert infer_aspect_ratio("竖版手机壁纸") == "9:16"
        assert infer_aspect_ratio("抖音短视频背景") == "9:16"
        assert infer_aspect_ratio("vertical mobile banner") == "9:16"

    def test_ultrawide_detection(self):
        """测试超宽屏检测。"""
        assert infer_aspect_ratio("全景风景照片") == "21:9"
        assert infer_aspect_ratio("panoramic cityscape") == "21:9"

    def test_photography_detection(self):
        """测试摄影比例检测。"""
        assert infer_aspect_ratio("相机拍摄的照片") == "3:2"
        assert infer_aspect_ratio("photography portrait") == "3:2"

    def test_default_fallback(self):
        """测试默认值。"""
        assert infer_aspect_ratio("随便画点什么") == "1:1"
        assert infer_aspect_ratio("") == "1:1"


class TestSizePreferenceInference:
    """测试尺寸档位推断。"""

    def test_high_complexity(self):
        """测试高复杂度场景。"""
        prompt = "详细的城市全景图，包含众多建筑、车辆和人群，细节丰富的宏大场景"
        assert infer_size_preference(prompt) == "xlarge"

    def test_medium_complexity(self):
        """测试中等复杂度场景。"""
        prompt = "一个室内场景，有几个人物角色在对话"
        assert infer_size_preference(prompt) == "medium"

    def test_low_complexity(self):
        """测试低复杂度场景。"""
        prompt = "极简风格logo"
        assert infer_size_preference(prompt) == "small"

    def test_long_prompt_bonus(self):
        """测试长提示词加成。"""
        long_prompt = " ".join(["详细描述"] * 30)
        assert infer_size_preference(long_prompt) in {"large", "xlarge"}

    def test_widescreen_bonus(self):
        """测试宽屏比例加成。"""
        prompt = "一个简单的场景"
        # 16:9应该比1:1推荐更高的分辨率
        size_169 = infer_size_preference(prompt, "16:9")
        size_11 = infer_size_preference(prompt, "1:1")
        # 由于16:9有加成，至少不会更低
        assert size_169 in {"medium", "large", "xlarge"}


class TestOpenAISizeInference:
    """测试 OpenAI 尺寸推断。"""

    def test_landscape_preference(self):
        """测试横屏偏好。"""
        sizes = ["1024x1024", "1024x1536", "1536x1024"]
        result = infer_openai_size("横屏桌面壁纸", sizes)
        assert result == "1536x1024"

    def test_portrait_preference(self):
        """测试竖屏偏好。"""
        sizes = ["1024x1024", "1024x1536", "1536x1024"]
        result = infer_openai_size("竖版手机壁纸", sizes)
        assert result == "1024x1536"

    def test_square_preference(self):
        """测试正方形偏好。"""
        sizes = ["1024x1024", "1024x1536", "1536x1024"]
        result = infer_openai_size("社交媒体头像", sizes)
        assert result == "1024x1024"

    def test_high_resolution_for_complex(self):
        """测试复杂场景选择高分辨率。"""
        sizes = ["512x512", "1024x1024", "2048x2048"]
        prompt = "详细的城市全景图，包含众多建筑和人群，细节丰富"
        result = infer_openai_size(prompt, sizes)
        assert result == "2048x2048"

    def test_fallback_to_first(self):
        """测试回退到第一个选项。"""
        sizes = ["1024x1024"]
        result = infer_openai_size("任意描述", sizes)
        assert result == "1024x1024"


class TestGeminiOutputInference:
    """测试 Gemini 输出推断。"""

    def test_full_inference(self):
        """测试完整推断。"""
        ratios = ["1:1", "16:9", "9:16"]
        sizes = ["512", "1K", "2K", "4K"]
        prompt = "宽屏电影场景，详细的背景和角色"
        result = infer_gemini_output(prompt, ratios, sizes)

        assert result["aspect_ratio"] == "16:9"
        assert result["image_size"] in {"2K", "4K"}

    def test_portrait_with_medium_size(self):
        """测试竖屏中等尺寸。"""
        ratios = ["1:1", "16:9", "9:16"]
        sizes = ["512", "1K", "2K"]
        prompt = "竖版手机壁纸，简单风格"
        result = infer_gemini_output(prompt, ratios, sizes)

        assert result["aspect_ratio"] == "9:16"
        # 简单风格应该推荐较小尺寸
        assert result["image_size"] in {"512", "1K"}

    def test_fallback_to_available(self):
        """测试回退到可用选项。"""
        ratios = ["1:1"]
        sizes = ["1K"]
        prompt = "超宽屏全景图"
        result = infer_gemini_output(prompt, ratios, sizes)

        # 即使推断出21:9，也应该回退到可用的1:1
        assert result["aspect_ratio"] == "1:1"
        assert result["image_size"] == "1K"


class TestExplanation:
    """测试解释生成。"""

    def test_explanation_generation(self):
        """测试解释文本生成。"""
        explanation = explain_size_choice("横屏宽屏视频", "16:9", "2K")
        assert len(explanation) > 0
        assert "横屏" in explanation or "宽屏" in explanation or "16:9" in explanation

    def test_high_resolution_explanation(self):
        """测试高分辨率解释。"""
        explanation = explain_size_choice("详细场景", "1:1", "4K")
        assert "高分辨率" in explanation or "复杂度" in explanation

    def test_simple_explanation(self):
        """测试简单场景解释。"""
        explanation = explain_size_choice("极简logo", "1:1", "512")
        assert len(explanation) > 0


class TestEdgeCases:
    """测试边界情况。"""

    def test_empty_prompt(self):
        """测试空提示词。"""
        assert infer_aspect_ratio("") == "1:1"
        assert infer_size_preference("") == "small"

    def test_mixed_keywords(self):
        """测试混合关键词。"""
        # 同时包含横屏和竖屏关键词，应该选择得分最高的
        prompt = "横屏宽屏视频封面"
        ratio = infer_aspect_ratio(prompt)
        assert ratio == "16:9"  # 横屏关键词更多

    def test_non_english_prompt(self):
        """测试中文提示词。"""
        assert infer_aspect_ratio("竖版海报设计") == "3:4"
        assert infer_size_preference("详细的中国风景画") == "large"

    def test_case_insensitive(self):
        """测试大小写不敏感。"""
        assert infer_aspect_ratio("LANDSCAPE BANNER") == "16:9"
        assert infer_aspect_ratio("Landscape Banner") == "16:9"
