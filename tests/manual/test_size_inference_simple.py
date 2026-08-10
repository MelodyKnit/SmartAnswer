"""直接测试智能尺寸推断功能（主动调用脚本，非 pytest 单元测试）。

运行方式：
    conda run -n ai-study-qb python tests/manual/test_size_inference_simple.py
"""

import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.llm.image_generation.size_inference import (
    infer_aspect_ratio,
    infer_size_preference,
    infer_openai_size,
    infer_gemini_output,
    explain_size_choice,
)

print("=" * 60)
print("测试智能尺寸推断功能")
print("=" * 60)

# 测试1: 画幅比例推断
print("\n【测试1】画幅比例推断:")
test_cases = [
    ("一个方形的logo设计", "1:1"),
    ("横屏宽屏电影场景", "16:9"),
    ("竖版手机壁纸", "9:16"),
    ("全景风景照片", "21:9"),
    ("相机拍摄的人物照片", "3:2"),
]

for prompt, expected in test_cases:
    result = infer_aspect_ratio(prompt)
    status = "✓" if result == expected else "✗"
    print(f"  {status} '{prompt}' -> {result} (期望: {expected})")

# 测试2: 尺寸档位推断
print("\n【测试2】尺寸档位推断:")
complexity_cases = [
    ("详细的城市全景图，包含众多建筑、车辆和人群", "xlarge"),
    ("一个室内场景，有几个人物", "medium"),
    ("极简风格logo", "small"),
]

for prompt, expected in complexity_cases:
    result = infer_size_preference(prompt)
    status = "✓" if result == expected else "✗"
    print(f"  {status} '{prompt[:30]}...' -> {result} (期望: {expected})")

# 测试3: OpenAI 尺寸推断
print("\n【测试3】OpenAI 尺寸推断:")
sizes = ["1024x1024", "1024x1536", "1536x1024"]
openai_cases = [
    ("横屏桌面壁纸", "1536x1024"),
    ("竖版手机壁纸", "1024x1536"),
    ("社交媒体头像", "1024x1024"),
]

for prompt, expected in openai_cases:
    result = infer_openai_size(prompt, sizes)
    status = "✓" if result == expected else "✗"
    print(f"  {status} '{prompt}' -> {result} (期望: {expected})")

# 测试4: Gemini 输出推断
print("\n【测试4】Gemini 输出推断:")
ratios = ["1:1", "16:9", "9:16", "21:9"]
gemini_sizes = ["512", "1K", "2K", "4K"]

gemini_cases = [
    ("宽屏电影场景，详细的背景和角色", {"aspect_ratio": "16:9"}),
    ("竖版手机壁纸，简单风格", {"aspect_ratio": "9:16"}),
    ("正方形社交媒体图片", {"aspect_ratio": "1:1"}),
]

for prompt, expected in gemini_cases:
    result = infer_gemini_output(prompt, ratios, gemini_sizes)
    status = "✓" if result["aspect_ratio"] == expected["aspect_ratio"] else "✗"
    print(f"  {status} '{prompt[:30]}...' -> {result['aspect_ratio']} / {result['image_size']}")

# 测试5: 解释生成
print("\n【测试5】解释文本生成:")
explanations = [
    ("横屏宽屏视频", "16:9", "2K"),
    ("详细场景", "1:1", "4K"),
    ("极简logo", "1:1", "512"),
]

for prompt, ratio, size in explanations:
    result = explain_size_choice(prompt, ratio, size)
    print(f"  ✓ '{prompt}' -> '{result}'")

# 测试6: 边界情况
print("\n【测试6】边界情况:")
edge_cases = [
    ("", infer_aspect_ratio, "1:1", "空提示词"),
    ("LANDSCAPE BANNER", infer_aspect_ratio, "16:9", "大写英文"),
    ("横屏宽屏视频封面", infer_aspect_ratio, "16:9", "混合关键词"),
]

for prompt, func, expected, desc in edge_cases:
    result = func(prompt)
    status = "✓" if result == expected else "✗"
    print(f"  {status} {desc}: '{prompt}' -> {result}")

print("\n" + "=" * 60)
print("测试完成！")
print("=" * 60)
