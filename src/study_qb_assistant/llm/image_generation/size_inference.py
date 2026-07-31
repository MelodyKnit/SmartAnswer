"""智能尺寸推断：基于用户描述自动推荐最合适的图片尺寸和画幅。"""

from __future__ import annotations

import re
from typing import Literal

# 关键词到画幅比例的映射
ASPECT_RATIO_KEYWORDS = {
    "1:1": [
        "正方形", "方形", "头像", "logo", "图标", "icon", "社交媒体", "instagram", "微信",
        "square", "profile", "avatar",
    ],
    "16:9": [
        "横屏", "宽屏", "电影", "视频", "YouTube", "B站", "哔哩哔哩", "桌面壁纸",
        "landscape", "widescreen", "cinematic", "video", "banner", "cover",
    ],
    "9:16": [
        "竖屏", "手机", "竖版", "短视频", "抖音", "快手", "stories", "reels",
        "portrait", "vertical", "mobile", "phone",
    ],
    "4:3": [
        "传统", "经典", "演示文稿", "幻灯片", "PPT", "presentation", "classic",
    ],
    "3:4": [
        "竖版海报", "宣传画", "竖图", "portrait poster",
    ],
    "21:9": [
        "超宽", "全景", "panoramic", "ultrawide",
    ],
    "3:2": [
        "相机", "摄影", "照片", "photography", "camera",
    ],
    "2:3": [
        "竖版照片", "portrait photo",
    ],
}

# 内容复杂度关键词
COMPLEXITY_KEYWORDS = {
    "high": [
        "详细", "复杂", "精致", "细节丰富", "宏大场景", "全景", "大场景", "史诗",
        "detailed", "complex", "intricate", "elaborate", "epic", "panoramic",
        "城市", "建筑群", "人群", "多人", "landscape", "cityscape",
    ],
    "medium": [
        "场景", "环境", "室内", "室外", "人物", "角色", "动物",
        "scene", "environment", "character", "person", "animal",
    ],
    "low": [
        "简单", "极简", "单色", "纯色", "图标", "logo", "符号", "抽象",
        "simple", "minimal", "minimalist", "icon", "symbol", "abstract", "flat",
    ],
}

SizePreference = Literal["small", "medium", "large", "xlarge"]


def infer_aspect_ratio(prompt: str) -> str:
    """
    根据用户提示词推断最合适的画幅比例。

    Args:
        prompt: 用户输入的图片描述

    Returns:
        推荐的画幅比例，如 "16:9", "1:1" 等
    """
    prompt_lower = prompt.lower()

    # 统计每个画幅比例的匹配得分
    scores: dict[str, int] = {}

    for ratio, keywords in ASPECT_RATIO_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            if keyword.lower() in prompt_lower:
                # 关键词越长，匹配越精确，得分越高
                score += len(keyword)
        if score > 0:
            scores[ratio] = score

    # 返回得分最高的画幅比例
    if scores:
        return max(scores.items(), key=lambda x: x[1])[0]

    # 默认返回 1:1（最通用）
    return "1:1"


def infer_size_preference(prompt: str, aspect_ratio: str = "1:1") -> SizePreference:
    """
    根据提示词的内容复杂度推断推荐的像素档位。

    Args:
        prompt: 用户输入的图片描述
        aspect_ratio: 画幅比例

    Returns:
        推荐的尺寸级别：small(512), medium(1K), large(2K), xlarge(4K)
    """
    prompt_lower = prompt.lower()

    # 计算复杂度得分
    complexity_score = 0

    for level, keywords in COMPLEXITY_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in prompt_lower:
                if level == "high":
                    complexity_score += 3
                elif level == "medium":
                    complexity_score += 2
                else:
                    complexity_score += 1

    # 检查提示词长度（越长通常越复杂）
    word_count = len(prompt.split())
    if word_count > 50:
        complexity_score += 3
    elif word_count > 30:
        complexity_score += 2
    elif word_count > 15:
        complexity_score += 1

    # 根据画幅比例调整（宽屏通常需要更高分辨率）
    if aspect_ratio in {"16:9", "21:9"}:
        complexity_score += 1

    # 映射到尺寸级别
    if complexity_score >= 8:
        return "xlarge"  # 4K
    elif complexity_score >= 5:
        return "large"   # 2K
    elif complexity_score >= 3:
        return "medium"  # 1K
    else:
        return "small"   # 512


def infer_openai_size(prompt: str, available_sizes: list[str]) -> str:
    """
    为 OpenAI 模型推断最合适的预设尺寸。

    Args:
        prompt: 用户输入的图片描述
        available_sizes: 可用的预设尺寸列表，如 ["1024x1024", "1024x1536"]

    Returns:
        推荐的尺寸字符串
    """
    prompt_lower = prompt.lower()

    # 检测方向偏好
    has_landscape = any(kw in prompt_lower for kw in ["横屏", "宽屏", "landscape", "wide", "banner"])
    has_portrait = any(kw in prompt_lower for kw in ["竖屏", "竖版", "portrait", "vertical"])

    # 解析可用尺寸
    size_info = []
    for size in available_sizes:
        match = re.match(r"(\d+)x(\d+)", size)
        if match:
            width, height = int(match.group(1)), int(match.group(2))
            ratio = width / height
            size_info.append((size, width, height, ratio))

    if not size_info:
        return available_sizes[0] if available_sizes else "1024x1024"

    # 根据方向筛选
    if has_landscape and not has_portrait:
        # 横屏：宽 > 高
        candidates = [s for s in size_info if s[3] > 1.0]
    elif has_portrait and not has_landscape:
        # 竖屏：高 > 宽
        candidates = [s for s in size_info if s[3] < 1.0]
    else:
        # 无明确方向或同时要求：优先正方形，其次横屏
        square = [s for s in size_info if abs(s[3] - 1.0) < 0.1]
        if square:
            candidates = square
        else:
            candidates = size_info

    if not candidates:
        candidates = size_info

    # 根据复杂度选择分辨率
    complexity = infer_size_preference(prompt)

    # 按总像素数排序
    candidates = sorted(candidates, key=lambda x: x[1] * x[2], reverse=True)

    if complexity == "xlarge":
        return candidates[0][0]  # 最大
    elif complexity == "large":
        return candidates[min(1, len(candidates) - 1)][0]
    elif complexity == "medium":
        mid = len(candidates) // 2
        return candidates[mid][0]
    else:
        return candidates[-1][0]  # 最小


def infer_gemini_output(prompt: str, available_ratios: list[str], available_sizes: list[str]) -> dict[str, str]:
    """
    为 Gemini 模型推断画幅比例和像素档位。

    Args:
        prompt: 用户输入的图片描述
        available_ratios: 可用的画幅比例列表
        available_sizes: 可用的像素档位列表

    Returns:
        包含 aspect_ratio 和 image_size 的字典
    """
    # 推断画幅比例
    preferred_ratio = infer_aspect_ratio(prompt)
    aspect_ratio = preferred_ratio if preferred_ratio in available_ratios else available_ratios[0]

    # 推断像素档位
    size_pref = infer_size_preference(prompt, aspect_ratio)

    # 映射到 Gemini 的档位
    size_map = {
        "small": "512",
        "medium": "1K",
        "large": "2K",
        "xlarge": "4K",
    }

    preferred_size = size_map[size_pref]
    # 标准化（Gemini 使用大写 K）
    normalized_available = [s.upper() if s.lower().endswith("k") else s for s in available_sizes]
    image_size = preferred_size if preferred_size in normalized_available else normalized_available[0]

    return {
        "aspect_ratio": aspect_ratio,
        "image_size": image_size,
    }


def explain_size_choice(prompt: str, aspect_ratio: str, size: str) -> str:
    """
    生成尺寸选择的解释文本。

    Args:
        prompt: 用户输入的图片描述
        aspect_ratio: 选择的画幅比例
        size: 选择的尺寸

    Returns:
        解释文本
    """
    reasons = []

    prompt_lower = prompt.lower()

    # 解释画幅选择
    if aspect_ratio == "16:9":
        reasons.append("检测到横屏/宽屏关键词")
    elif aspect_ratio == "9:16":
        reasons.append("检测到竖屏/手机关键词")
    elif aspect_ratio == "1:1":
        reasons.append("适合社交媒体和通用场景")

    # 解释尺寸选择
    if "4K" in size or "2K" in size:
        reasons.append("内容复杂度较高，推荐高分辨率")
    elif "512" in size:
        reasons.append("简约风格，标准分辨率即可")
    else:
        reasons.append("标准分辨率适合大多数场景")

    return " · ".join(reasons) if reasons else "根据描述智能推荐"
