"""品牌 Logo 图像处理与裁剪逻辑。"""

from __future__ import annotations

import io
import warnings
from pathlib import Path

from PIL import Image, UnidentifiedImageError

MAX_BRAND_LOGO_PIXELS = 16_000_000


class BrandLogoError(ValueError):
    """品牌 Logo 图片无法安全处理。"""


def process_and_save_brand_logo(
    content_bytes: bytes, target_dir: Path
) -> dict[str, str]:
    """
    对上传的原始图片进行正方形裁剪和缩放，保存为不同分辨率的 PNG 格式文件。
    裁剪逻辑：取图像短边作为正方形的边长，左右或上下居中裁剪。

    保存的文件包括：
    1. logo_original.png: 原始大小，若边长大于 512px，则缩放至 512px。
    2. logo_lg.png: 128x128 像素
    3. logo_md.png: 64x64 像素
    4. logo_sm.png: 32x32 像素

    返回各文件相对于根路径的路径映射，如 {'original': '/media/brand/logo_original.png', ...}
    """
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content_bytes)) as source_img:
                width, height = source_img.size
                if width <= 0 or height <= 0:
                    raise BrandLogoError("图片尺寸不正确")
                if width * height > MAX_BRAND_LOGO_PIXELS:
                    raise BrandLogoError("图片像素过大，请上传更小的 Logo 图片")
                # 转为 RGBA 后再裁剪，保证透明背景和后续缩放行为一致。
                img = source_img.convert("RGBA")
    except BrandLogoError:
        raise
    except (Image.DecompressionBombWarning, UnidentifiedImageError, OSError) as exc:
        raise BrandLogoError("上传文件不是可识别的图片") from exc

    width, height = img.size

    # 计算居中正方形裁剪范围
    size = min(width, height)
    left = (width - size) // 2
    top = (height - size) // 2
    right = left + size
    bottom = top + size

    cropped_img = img.crop((left, top, right, bottom))

    # 尺寸映射定义
    sizes = {
        "original": 512 if size > 512 else size,
        "lg": 128,
        "md": 64,
        "sm": 32,
    }

    result_paths = {}

    for key, resolution in sizes.items():
        # 大图原始比例保留上限以防性能开销，其他分辨率直接缩放
        resized_img = cropped_img.resize(
            (resolution, resolution), Image.Resampling.LANCZOS
        )

        filename = f"logo_{key}.png"
        file_path = target_dir / filename

        # 保存为 PNG
        resized_img.save(file_path, "PNG")
        result_paths[key] = f"/media/brand/{filename}"

    return result_paths
