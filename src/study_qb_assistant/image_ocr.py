"""图片题 OCR 兜底能力。

OCR 只作为图片题的恢复路径：依赖未安装、图片不可访问或识别失败时返回 None，
由调用方继续走明确异常响应，避免把不可读图片伪装成低质量文本题。
"""

from __future__ import annotations

import base64
import binascii
import ipaddress
import re
import socket
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .input_anomalies import is_image_data_url, normalize_image_data_urls, normalize_image_urls
from .models import QuestionQuery

MAX_IMAGE_BYTES = 5 * 1024 * 1024
DATA_URL_PREFIX_PATTERN = re.compile(r"^data:(image/[-+.\w]+);base64,", re.I)


@dataclass(slots=True)
class ImageAsset:
    """统一描述一次可用于识图的图片资产。"""

    source_url: str
    mime_type: str
    content_bytes: bytes
    data_url: str


def build_ocr_query(query: QuestionQuery) -> QuestionQuery | None:
    """从图片 URL 尝试识别题干和选项，成功时返回文本化查询。"""

    texts: list[str] = []
    for asset in load_query_image_assets(query):
        text = ocr_image_bytes(asset.content_bytes)
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


def build_model_query(query: QuestionQuery) -> QuestionQuery:
    """为视觉模型补齐可直接传输的图片 data URL。"""

    if query.image_data_urls or query.option_image_data_urls:
        return query
    assets = load_query_image_assets(query)
    if not assets:
        return query
    data_urls = tuple(asset.data_url for asset in assets)
    return QuestionQuery(
        title=query.title,
        options=query.options,
        question_type=query.question_type,
        request_id=query.request_id,
        page_url=query.page_url,
        image_urls=query.image_urls,
        image_data_urls=data_urls,
        option_image_urls=dict(query.option_image_urls),
        option_image_data_urls=dict(query.option_image_data_urls),
    )


def load_query_image_assets(query: QuestionQuery) -> tuple[ImageAsset, ...]:
    """统一装载题目中的图片资产，优先使用浏览器侧传来的 data URL。"""

    assets: list[ImageAsset] = []
    seen: set[str] = set()
    for data_url in normalize_image_data_urls(
        query.image_data_urls,
        query.option_image_data_urls.values(),
    ):
        asset = decode_image_data_url(data_url)
        if asset is None:
            continue
        key = f"data:{hash(asset.data_url)}"
        if key in seen:
            continue
        seen.add(key)
        assets.append(asset)

    for url in normalize_image_urls(query.image_urls, (query.title,), query.option_image_urls.values()):
        if url in seen:
            continue
        asset = fetch_public_image_asset(url, referer=query.page_url)
        if asset is None:
            continue
        seen.add(url)
        assets.append(asset)
    return tuple(assets)


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


def fetch_public_image_asset(url: str, *, referer: str | None = None) -> ImageAsset | None:
    """抓取图片并转换成带 mime/data-url 的统一资产对象。"""

    image, mime_type = fetch_public_image_with_mime(url)
    if image is None or not mime_type:
        image, mime_type = fetch_image_via_playwright(url, referer=referer)
    if image is None or not mime_type:
        return None
    data_url = image_bytes_to_data_url(image, mime_type)
    if not data_url:
        return None
    return ImageAsset(source_url=url, mime_type=mime_type, content_bytes=image, data_url=data_url)


def fetch_public_image_with_mime(url: str) -> tuple[bytes | None, str | None]:
    """安全抓取公网图片，同时返回识别出的 mime type。"""

    if not is_public_http_url(url):
        return None, None
    try:
        with httpx.stream("GET", url, timeout=10.0, follow_redirects=True) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
            if content_type and not content_type.startswith("image/"):
                return None, None
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > MAX_IMAGE_BYTES:
                    return None, None
                chunks.append(chunk)
            mime_type = content_type or guess_image_mime(url)
            return b"".join(chunks), mime_type
    except Exception:
        return None, None


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


def decode_image_data_url(data_url: str) -> ImageAsset | None:
    """把浏览器上传的图片 data URL 解码为统一资产对象。"""

    text = str(data_url or "").strip()
    if not is_image_data_url(text):
        return None
    match = DATA_URL_PREFIX_PATTERN.match(text)
    if not match:
        return None
    mime_type = match.group(1).lower()
    payload = text[match.end() :]
    try:
        content = base64.b64decode(payload, validate=True)
    except (ValueError, binascii.Error):
        return None
    if not content or len(content) > MAX_IMAGE_BYTES:
        return None
    return ImageAsset(
        source_url="inline-data-url",
        mime_type=mime_type,
        content_bytes=content,
        data_url=text,
    )


def image_bytes_to_data_url(content: bytes, mime_type: str) -> str:
    """把图片字节编码成可直接发送给视觉模型的 data URL。"""

    if not content or not mime_type.startswith("image/"):
        return ""
    payload = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type};base64,{payload}"


def fetch_image_via_playwright(url: str, *, referer: str | None = None) -> tuple[bytes | None, str | None]:
    """使用 Playwright 以浏览器导航方式抓取图片，绕过部分防盗链限制。"""

    if not is_public_http_url(url):
        return None, None
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, None
    try:
        from .llm.providers.web_search import resolve_browser_path
    except Exception:
        resolve_browser_path = None
    browser_path = resolve_browser_path() if callable(resolve_browser_path) else None
    if not browser_path:
        return None, None

    manager = None
    browser = None
    context = None
    page = None
    try:
        manager = sync_playwright().start()
        browser = manager.chromium.launch(executable_path=browser_path, headless=True)
        headers = {"Referer": str(referer).strip()} if str(referer or "").strip() else None
        context = browser.new_context(extra_http_headers=headers or {})
        page = context.new_page()
        response = page.goto(url, wait_until="domcontentloaded", timeout=10000)
        if response is None or not response.ok:
            return None, None
        mime_type = (response.headers.get("content-type", "").split(";", 1)[0].lower() or guess_image_mime(url))
        if mime_type and not mime_type.startswith("image/"):
            return None, None
        body = response.body()
        if not body or len(body) > MAX_IMAGE_BYTES:
            return None, None
        return body, mime_type
    except Exception:
        return None, None
    finally:
        try:
            if page is not None:
                page.close()
        except Exception:
            pass
        try:
            if context is not None:
                context.close()
        except Exception:
            pass
        try:
            if browser is not None:
                browser.close()
        except Exception:
            pass
        try:
            if manager is not None:
                manager.stop()
        except Exception:
            pass


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


def guess_image_mime(url: str) -> str:
    """根据图片 URL 后缀猜测 mime type。"""

    lowered = str(url or "").strip().lower()
    if lowered.endswith(".png"):
        return "image/png"
    if lowered.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lowered.endswith(".webp"):
        return "image/webp"
    if lowered.endswith(".gif"):
        return "image/gif"
    if lowered.endswith(".bmp"):
        return "image/bmp"
    return ""
