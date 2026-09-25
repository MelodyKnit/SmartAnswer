"""帮助文档公开接口路由。免登录即可获取 docs/help 下的 markdown 文章列表与内容。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from starlette.responses import JSONResponse

DOCS_DIR = Path(__file__).resolve().parents[5] / "docs" / "help"

FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """解析 Markdown 顶部的 YAML Frontmatter（简单键值），返回 (metadata, body)。"""
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        return {}, text

    meta_str = match.group(1)
    body = text[match.end() :]
    meta: dict[str, Any] = {}
    for line in meta_str.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            if val.isdigit():
                meta[key] = int(val)
            else:
                meta[key] = val
    return meta, body


def read_all_help_docs() -> list[dict[str, Any]]:
    """读取 docs/help/ 目录下的所有 .md 文件并组织返回。"""
    if not DOCS_DIR.exists() or not DOCS_DIR.is_dir():
        return []

    docs: list[dict[str, Any]] = []
    for path in sorted(DOCS_DIR.glob("*.md")):
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            continue
        meta, body = parse_frontmatter(raw)
        filename_id = path.stem.lower()
        # 去掉如 "01-" 这样的前缀作为备用 id
        if "-" in filename_id and filename_id.split("-", 1)[0].isdigit():
            fallback_id = filename_id.split("-", 1)[1]
        else:
            fallback_id = filename_id

        doc_id = meta.get("id") or fallback_id
        doc_title = meta.get("title") or fallback_id
        category = meta.get("category") or "常用指南"
        icon = meta.get("icon") or "Document"
        order = meta.get("order") or 999
        description = meta.get("description") or ""

        docs.append(
            {
                "id": str(doc_id),
                "title": str(doc_title),
                "category": str(category),
                "icon": str(icon),
                "order": int(order),
                "description": str(description),
                "content": body,
            }
        )

    # 按照 order 排序
    docs.sort(key=lambda x: (x["order"], x["id"]))
    return docs


def build_help_router() -> APIRouter:
    """构建帮助文档公开路由。"""
    router = APIRouter()

    @router.get("/help/docs")
    def list_help_docs() -> JSONResponse:
        """获取所有帮助文档列表与正文。免登录公开访问。"""
        docs = read_all_help_docs()
        return JSONResponse({"docs": docs})

    return router
