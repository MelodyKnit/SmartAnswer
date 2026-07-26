"""生图调用协议的配置、输出选项与校验策略。"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any


GEMINI_NATIVE_PROVIDER = "gemini-native"
OPENAI_IMAGES_PROVIDER = "openai-images"
OPENAI_COMPATIBLE_IMAGES_PROVIDER = "openai-compatible-images"
LEGACY_OPENAI_CHAT_IMAGE_PROVIDER = "openai-chat-image"

SUPPORTED_IMAGE_PROVIDERS = frozenset(
    {
        GEMINI_NATIVE_PROVIDER,
        OPENAI_IMAGES_PROVIDER,
        OPENAI_COMPATIBLE_IMAGES_PROVIDER,
        LEGACY_OPENAI_CHAT_IMAGE_PROVIDER,
    }
)
OPENAI_IMAGES_PROVIDERS = frozenset(
    {OPENAI_IMAGES_PROVIDER, OPENAI_COMPATIBLE_IMAGES_PROVIDER}
)

GEMINI_ASPECT_RATIOS = frozenset(
    {
        "1:1",
        "1:4",
        "4:1",
        "1:8",
        "8:1",
        "2:3",
        "3:2",
        "3:4",
        "4:3",
        "4:5",
        "5:4",
        "9:16",
        "16:9",
        "21:9",
    }
)
GEMINI_IMAGE_SIZES = frozenset({"512", "1K", "2K", "4K"})
DEFAULT_OPENAI_PRESET_SIZES = ("1024x1024", "1024x1536", "1536x1024")
DEFAULT_CUSTOM_SIZE_CONSTRAINTS = {
    "min_width": 512,
    "max_width": 3840,
    "min_height": 512,
    "max_height": 3840,
    "step": 16,
    "min_pixels": 655_360,
    "max_pixels": 8_294_400,
}
SIZE_PATTERN = re.compile(r"^(?P<width>[1-9]\d{1,4})x(?P<height>[1-9]\d{1,4})$")


class ImageGenerationProtocolError(ValueError):
    """协议配置或输出参数不符合当前模型可用能力。"""


def normalize_protocol_config(
    provider: str,
    value: object,
    *,
    legacy_capabilities: object = None,
) -> dict[str, Any]:
    """归一化并严格校验模型协议配置，拒绝任意上游请求模板。"""

    config = json_object(value, field_name="协议配置")
    legacy_sizes = legacy_preset_sizes(legacy_capabilities)
    if provider == GEMINI_NATIVE_PROVIDER:
        reject_unknown_keys(config, {"auth_mode", "aspect_ratios", "image_sizes"})
        auth_mode = str(config.get("auth_mode") or "x-goog-api-key").strip().lower()
        if auth_mode not in {"x-goog-api-key", "bearer"}:
            raise ImageGenerationProtocolError("Gemini 鉴权方式仅支持 x-goog-api-key 或 bearer")
        aspect_ratios = normalize_string_list(
            config.get("aspect_ratios"), default=("1:1",), field_name="Gemini 画幅比例"
        )
        unknown_ratios = sorted(set(aspect_ratios) - GEMINI_ASPECT_RATIOS)
        if unknown_ratios:
            raise ImageGenerationProtocolError(
                f"不支持的 Gemini 画幅比例: {', '.join(unknown_ratios)}"
            )
        image_sizes = [item.upper() if item.lower().endswith("k") else item for item in normalize_string_list(
            config.get("image_sizes"), default=("1K",), field_name="Gemini 像素档位"
        )]
        unknown_sizes = sorted(set(image_sizes) - GEMINI_IMAGE_SIZES)
        if unknown_sizes:
            raise ImageGenerationProtocolError(
                f"不支持的 Gemini 像素档位: {', '.join(unknown_sizes)}"
            )
        return {
            "auth_mode": auth_mode,
            "aspect_ratios": unique_values(aspect_ratios),
            "image_sizes": unique_values(image_sizes),
        }

    if provider in OPENAI_IMAGES_PROVIDERS:
        reject_unknown_keys(
            config,
            {"preset_sizes", "allow_custom_size", "custom_size_constraints"},
        )
        preset_sizes = normalize_size_list(
            config.get("preset_sizes"),
            default=legacy_sizes or DEFAULT_OPENAI_PRESET_SIZES,
            field_name="预设尺寸",
        )
        allow_custom_size = normalize_bool(config.get("allow_custom_size"), default=False)
        if provider == OPENAI_COMPATIBLE_IMAGES_PROVIDER and allow_custom_size:
            raise ImageGenerationProtocolError("通用兼容 Images 协议不支持自定义尺寸")
        normalized: dict[str, Any] = {
            "preset_sizes": preset_sizes,
            "allow_custom_size": allow_custom_size,
        }
        if provider == OPENAI_IMAGES_PROVIDER:
            normalized["custom_size_constraints"] = normalize_custom_size_constraints(
                config.get("custom_size_constraints"),
                enabled=allow_custom_size,
            )
        return normalized

    if provider == LEGACY_OPENAI_CHAT_IMAGE_PROVIDER:
        reject_unknown_keys(config, {"mode"})
        return {"mode": "model-controlled"}

    raise ImageGenerationProtocolError(f"暂不支持的生图提供商: {provider}")


def capabilities_for_protocol(
    provider: str,
    protocol_config: Mapping[str, Any],
    *,
    legacy_capabilities: object = None,
) -> list[str]:
    """保留旧能力字段，同时以结构化协议配置作为新行为的唯一依据。"""

    if provider in OPENAI_IMAGES_PROVIDERS:
        return ["text-to-image", *list(protocol_config["preset_sizes"])]
    if provider == LEGACY_OPENAI_CHAT_IMAGE_PROVIDER:
        return ["text-to-image", *legacy_preset_sizes(legacy_capabilities)]
    return ["text-to-image"]


def public_output_capabilities(provider: str, protocol_config: Mapping[str, Any]) -> dict[str, Any]:
    """构建前端可直接渲染的输出能力，不输出密钥或供应商私有参数。"""

    if provider == GEMINI_NATIVE_PROVIDER:
        return {
            "kind": "gemini",
            "aspect_ratios": list(protocol_config["aspect_ratios"]),
            "image_sizes": list(protocol_config["image_sizes"]),
        }
    if provider == OPENAI_IMAGES_PROVIDER:
        return {
            "kind": "openai-images",
            "preset_sizes": list(protocol_config["preset_sizes"]),
            "allow_custom_size": bool(protocol_config["allow_custom_size"]),
            "custom_size_constraints": dict(protocol_config["custom_size_constraints"]),
        }
    if provider == OPENAI_COMPATIBLE_IMAGES_PROVIDER:
        return {
            "kind": "compatible-images",
            "preset_sizes": list(protocol_config["preset_sizes"]),
            "allow_custom_size": False,
        }
    return {"kind": "model-controlled"}


def normalize_output_options(
    provider: str,
    protocol_config: Mapping[str, Any],
    *,
    size: object = "",
    output: object = None,
) -> tuple[str, dict[str, str]]:
    """将旧 ``size`` 或新版 ``output`` 归一为任务可复现的输出快照。"""

    raw_size = str(size or "").strip().lower()
    raw_output = json_object(output, field_name="输出参数") if output is not None else {}
    if raw_size and raw_output:
        raise ImageGenerationProtocolError("size 与 output 不能同时传入")

    if provider == GEMINI_NATIVE_PROVIDER:
        reject_unknown_keys(raw_output, {"aspect_ratio", "image_size"})
        aspect_ratio = str(raw_output.get("aspect_ratio") or protocol_config["aspect_ratios"][0]).strip()
        image_size = str(raw_output.get("image_size") or protocol_config["image_sizes"][0]).strip()
        image_size = image_size.upper() if image_size.lower().endswith("k") else image_size
        if aspect_ratio not in protocol_config["aspect_ratios"]:
            raise ImageGenerationProtocolError("当前 Gemini 模型不支持该画幅比例")
        if image_size not in protocol_config["image_sizes"]:
            raise ImageGenerationProtocolError("当前 Gemini 模型不支持该像素档位")
        return f"{aspect_ratio} · {image_size}", {
            "aspect_ratio": aspect_ratio,
            "image_size": image_size,
        }

    if provider in OPENAI_IMAGES_PROVIDERS:
        reject_unknown_keys(raw_output, {"size"})
        selected_size = str(raw_output.get("size") or raw_size or protocol_config["preset_sizes"][0]).strip().lower()
        normalized_size = normalize_size(selected_size, field_name="图片尺寸")
        if normalized_size not in protocol_config["preset_sizes"]:
            if provider != OPENAI_IMAGES_PROVIDER or not protocol_config["allow_custom_size"]:
                raise ImageGenerationProtocolError("当前生图模型不支持该图片尺寸")
            validate_custom_size(
                normalized_size,
                protocol_config["custom_size_constraints"],
            )
        return normalized_size, {"size": normalized_size}

    if provider == LEGACY_OPENAI_CHAT_IMAGE_PROVIDER:
        if raw_output:
            raise ImageGenerationProtocolError("当前聊天生图协议不支持指定图片尺寸")
        return "model-controlled", {"mode": "model-controlled"}

    raise ImageGenerationProtocolError(f"暂不支持的生图提供商: {provider}")


def json_object(value: object, *, field_name: str) -> dict[str, Any]:
    """解析持久化 JSON 或 API 对象，不接受数组和任意文本模板。"""

    if value is None or value == "":
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ImageGenerationProtocolError(f"{field_name}必须是 JSON 对象") from exc
        if isinstance(parsed, Mapping):
            return dict(parsed)
    raise ImageGenerationProtocolError(f"{field_name}必须是 JSON 对象")


def legacy_preset_sizes(value: object) -> list[str]:
    """从旧逗号能力字段提取合法预设尺寸，未知值不扩大新模型能力。"""

    values = value if isinstance(value, Sequence) and not isinstance(value, str) else str(value or "").split(",")
    sizes: list[str] = []
    for item in values:
        raw = str(item).strip().lower()
        if SIZE_PATTERN.fullmatch(raw):
            sizes.append(normalize_size(raw, field_name="预设尺寸"))
    return unique_values(sizes)


def normalize_string_list(value: object, *, default: Sequence[str], field_name: str) -> list[str]:
    """校验配置中的非空字符串数组并保持输入顺序。"""

    if value is None:
        values = list(default)
    elif isinstance(value, Sequence) and not isinstance(value, str):
        values = [str(item).strip() for item in value]
    else:
        raise ImageGenerationProtocolError(f"{field_name}必须是数组")
    normalized = unique_values([item for item in values if item])
    if not normalized:
        raise ImageGenerationProtocolError(f"{field_name}至少需要保留一项")
    return normalized


def normalize_size_list(value: object, *, default: Sequence[str], field_name: str) -> list[str]:
    """归一化声明给用户选择的预设宽高。"""

    values = normalize_string_list(value, default=default, field_name=field_name)
    return unique_values([normalize_size(item.lower(), field_name=field_name) for item in values])


def normalize_size(value: str, *, field_name: str) -> str:
    """验证 ``宽x高`` 格式并保留小写分隔符。"""

    matched = SIZE_PATTERN.fullmatch(value)
    if matched is None:
        raise ImageGenerationProtocolError(f"{field_name}必须使用 宽x高 格式")
    width = int(matched.group("width"))
    height = int(matched.group("height"))
    if width > 8192 or height > 8192:
        raise ImageGenerationProtocolError(f"{field_name}超出允许范围")
    return f"{width}x{height}"


def normalize_bool(value: object, *, default: bool) -> bool:
    """只接受布尔值，避免配置字符串隐式开启高成本能力。"""

    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ImageGenerationProtocolError("布尔配置必须使用 true 或 false")


def normalize_custom_size_constraints(value: object, *, enabled: bool) -> dict[str, int]:
    """归一化 OpenAI 原生模型已声明的自定义尺寸约束。"""

    if value is None:
        if not enabled:
            return dict(DEFAULT_CUSTOM_SIZE_CONSTRAINTS)
        value = DEFAULT_CUSTOM_SIZE_CONSTRAINTS
    raw = json_object(value, field_name="自定义尺寸约束")
    unknown = sorted(set(raw) - set(DEFAULT_CUSTOM_SIZE_CONSTRAINTS))
    if unknown:
        raise ImageGenerationProtocolError(f"不支持的自定义尺寸约束: {', '.join(unknown)}")
    normalized: dict[str, int] = {}
    for key, default in DEFAULT_CUSTOM_SIZE_CONSTRAINTS.items():
        try:
            parsed = int(raw.get(key, default))
        except (TypeError, ValueError) as exc:
            raise ImageGenerationProtocolError(f"自定义尺寸约束 {key} 必须是整数") from exc
        if parsed <= 0:
            raise ImageGenerationProtocolError(f"自定义尺寸约束 {key} 必须大于 0")
        normalized[key] = parsed
    if normalized["min_width"] > normalized["max_width"] or normalized["min_height"] > normalized["max_height"]:
        raise ImageGenerationProtocolError("自定义尺寸最小值不能大于最大值")
    if normalized["min_pixels"] > normalized["max_pixels"]:
        raise ImageGenerationProtocolError("自定义像素总数最小值不能大于最大值")
    return normalized


def validate_custom_size(size: str, constraints: Mapping[str, Any]) -> None:
    """校验用户自定义尺寸不超过模型已声明的能力边界。"""

    width_raw, height_raw = size.split("x", 1)
    width = int(width_raw)
    height = int(height_raw)
    normalized = normalize_custom_size_constraints(constraints, enabled=True)
    if not (normalized["min_width"] <= width <= normalized["max_width"]):
        raise ImageGenerationProtocolError("自定义图片宽度超出当前模型允许范围")
    if not (normalized["min_height"] <= height <= normalized["max_height"]):
        raise ImageGenerationProtocolError("自定义图片高度超出当前模型允许范围")
    if width % normalized["step"] or height % normalized["step"]:
        raise ImageGenerationProtocolError(
            f"自定义图片宽高必须是 {normalized['step']} 的整数倍"
        )
    pixels = width * height
    if not (normalized["min_pixels"] <= pixels <= normalized["max_pixels"]):
        raise ImageGenerationProtocolError("自定义图片总像素超出当前模型允许范围")


def reject_unknown_keys(value: Mapping[str, Any], allowed: set[str]) -> None:
    """拒绝未知协议字段，避免配置成为任意上游请求模板。"""

    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ImageGenerationProtocolError(f"不支持的协议配置字段: {', '.join(unknown)}")


def unique_values(values: Sequence[str]) -> list[str]:
    """按原顺序去重，保证前端默认值稳定。"""

    return list(dict.fromkeys(values))
