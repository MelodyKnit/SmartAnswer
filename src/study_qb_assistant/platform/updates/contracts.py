"""公开 GitHub Release 查询使用的数据契约与输入校验。"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Literal
from urllib.parse import urlparse


SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
GITHUB_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

ProjectUpdateState = Literal["unavailable", "idle", "failed"]
ProjectUpdateVersionRelation = Literal["unknown", "behind", "current", "ahead"]


class ProjectUpdateError(Exception):
    """表示可安全返回给管理员的公开 Release 查询失败。"""

    def __init__(self, code: str, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


@dataclass(frozen=True, slots=True)
class ProjectUpdateRelease:
    """经过 Release manifest 校验的公开版本摘要。"""

    version: str
    tag: str
    name: str
    body: str
    published_at: str
    html_url: str
    image: str
    image_digest: str
    build_sha: str

    def to_dict(self) -> dict[str, str]:
        """转换为不含敏感配置的 API 响应。"""

        return asdict(self)


def normalize_version(value: object) -> str:
    """校验三段语义版本并返回无 ``v`` 前缀的值。"""

    version = str(value or "").strip().removeprefix("v")
    if not SEMVER_RE.fullmatch(version):
        raise ValueError("版本号必须为 X.Y.Z 格式")
    return version


def compare_versions(left: str, right: str) -> int:
    """比较两个已校验的三段语义版本。"""

    left_parts = tuple(int(part) for part in normalize_version(left).split("."))
    right_parts = tuple(int(part) for part in normalize_version(right).split("."))
    return (left_parts > right_parts) - (left_parts < right_parts)


def normalize_github_repository(value: object) -> str:
    """归一化 ``owner/repository`` 或 GitHub 仓库 URL。"""

    raw = str(value or "").strip().removesuffix("/")
    if raw.startswith("git@github.com:"):
        raw = raw.removeprefix("git@github.com:")
    elif raw.startswith("https://") or raw.startswith("http://"):
        parsed = urlparse(raw)
        if parsed.hostname != "github.com":
            raise ValueError("更新仓库必须位于 github.com")
        raw = parsed.path.strip("/")
    raw = raw.removesuffix(".git")
    if not GITHUB_REPOSITORY_RE.fullmatch(raw):
        raise ValueError("GitHub 仓库必须使用 owner/repository 格式")
    return raw
