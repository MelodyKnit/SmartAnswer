"""项目更新领域的稳定数据契约与输入校验。"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Literal
from urllib.parse import urlparse


SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
GITHUB_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
WORKFLOW_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.ya?ml$")
OPERATION_ID_RE = re.compile(r"^[0-9a-f]{32}$")

ProjectUpdateState = Literal[
    "disabled", "unconfigured", "idle", "queued", "running", "succeeded", "failed"
]


class ProjectUpdateError(Exception):
    """表示可安全返回给管理员的项目更新失败。"""

    def __init__(self, code: str, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


@dataclass(frozen=True, slots=True)
class ProjectUpdateRelease:
    """经过 GitHub Release manifest 校验后的可部署版本。"""

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
        """转换为不含凭据的 API 负载。"""

        return asdict(self)


@dataclass(frozen=True, slots=True)
class ProjectUpdateConfiguration:
    """项目更新运行所需的已归一化配置。"""

    enabled: bool
    configured: bool
    automatic_check_enabled: bool
    check_interval_hours: int
    repository: str
    workflow: str
    token: str

    @property
    def check_interval_seconds(self) -> int:
        """返回后台巡检使用的秒级检查周期。"""

        return self.check_interval_hours * 60 * 60


@dataclass(frozen=True, slots=True)
class ProjectUpdateOperation:
    """一次 GitHub Actions 部署请求的可轮询状态。"""

    operation_id: str
    expected_version: str
    requested_by: str
    state: ProjectUpdateState
    created_at: float
    updated_at: float
    workflow_run_id: int = 0
    workflow_run_url: str = ""
    last_polled_at: float = 0.0
    message: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, str | float | int]:
        """转换为前端可轮询的状态数据。"""

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
    """归一化 ``owner/repository`` 或常见 GitHub 仓库 URL。"""

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


def normalize_workflow_file(value: object) -> str:
    """校验受控的 GitHub Actions 工作流文件名。"""

    workflow = str(value or "").strip()
    if not WORKFLOW_FILE_RE.fullmatch(workflow):
        raise ValueError("部署工作流必须是 .github/workflows 下的 YAML 文件名")
    return workflow


def valid_operation_id(value: object) -> str:
    """返回合法的操作 ID；非法数据返回空串。"""

    operation_id = str(value or "").strip().lower()
    return operation_id if OPERATION_ID_RE.fullmatch(operation_id) else ""
