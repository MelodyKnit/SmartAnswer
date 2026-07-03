"""图片题 OCR 兜底能力。

OCR 只作为图片题的恢复路径：依赖未安装、图片不可访问或识别失败时返回 None，
由调用方继续走明确异常响应，避免把不可读图片伪装成低质量文本题。
"""

from __future__ import annotations

import ipaddress
import re
import socket
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .input_anomalies import normalize_image_urls
from .models import QuestionQuery

MAX_IMAGE_BYTES = 5 * 1024 * 1024


def build_ocr_query(query: QuestionQuery) -> QuestionQuery | None:
    """从图片 URL 尝试识别题干和选项，成功时返回文本化查询。"""

    texts: list[str] = []
    for url in normalize_image_urls(query.image_urls, (query.title,), query.option_image_urls.values()):
        image = fetch_public_image(url)
        if image is None:
            continue
        text = ocr_image_bytes(image)
        if text:
            texts.append(text)
    if not texts:
        return None
    merged_text = "\n".join(texts)
    options = query.options or parse_options_from_ocr_text(merged_text)
    title = query.title
    if normalize_image_urls((title,)) or not title.strip():
        title = extract_title_from_ocr_text(merged_text, options)
    else:
        title = f"{title}\n图片 OCR 内容：{merged_text}"
    if not title.strip():
        return None
    return QuestionQuery(
        title=title.strip(),
        options=options,
        question_type=query.question_type,
        request_id=query.request_id,
    )


def fetch_public_image(url: str) -> bytes | None:
    """安全抓取公网图片，拒绝内网地址和超大响应。"""

    if not is_public_http_url(url):
        return None
    try:
        with httpx.stream("GET", url, timeout=10.0, follow_redirects=True) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if content_type and not content_type.startswith("image/"):
                return None
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > MAX_IMAGE_BYTES:
                    return None
                chunks.append(chunk)
            return b"".join(chunks)
    except Exception:
        return None


def is_public_http_url(url: str) -> bool:
    """校验 URL 是否是公网 HTTP(S) 地址，避免 SSRF。"""

    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        return False
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    return True


def ocr_image_bytes(image: bytes) -> str:
    """调用 RapidOCR 识别图片文本。"""

    try:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            from rapidocr import RapidOCR
    except ImportError:
        return ""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        handle.write(image)
        temp_path = Path(handle.name)
    try:
        engine = RapidOCR()
        result, _elapsed = engine(str(temp_path))
    except Exception:
        return ""
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
    lines: list[str] = []
    for item in result or []:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            text = str(item[1] or "").strip()
            if text:
                lines.append(text)
    return "\n".join(lines)


def parse_options_from_ocr_text(text: str) -> tuple[str, ...]:
    """从 OCR 文本中提取 A-D 选项。"""

    options: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^([A-F])[\s.．、:：]+(.+)$", line.strip(), re.I)
        if match and match.group(2).strip():
            options.append(f"{match.group(1).upper()}. {match.group(2).strip()}")
    return tuple(options)


def extract_title_from_ocr_text(text: str, options: tuple[str, ...]) -> str:
    """从 OCR 文本中提取题干，过滤已识别出的选项行。"""

    option_set = {option.strip() for option in options}
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped in option_set:
            continue
        if re.match(r"^[A-F][\s.．、:：]+", stripped, re.I):
            continue
        lines.append(stripped)
    return " ".join(lines[:4])
