"""项目更新命令和状态的数据契约。"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
OPERATION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
ACTIVE_STATES = {
    "queued",
    "checking",
    "downloading",
    "backing_up",
    "deploying",
    "verifying",
    "rolling_back",
}
TERMINAL_STATES = {"succeeded", "failed", "rolled_back", "rollback_failed"}
KNOWN_STATES = ACTIVE_STATES | TERMINAL_STATES | {"idle", "disabled", "unconfigured"}


def normalize_version(value: object) -> str:
    """校验并返回不带 ``v`` 前缀的三段语义版本号。"""

    version = str(value or "").strip().removeprefix("v")
    if not SEMVER_RE.fullmatch(version):
        raise ValueError("版本号必须为 X.Y.Z 格式")
    return version


def compare_versions(left: str, right: str) -> int:
    """比较两个已经校验的三段语义版本号。"""

    left_parts = tuple(int(part) for part in normalize_version(left).split("."))
    right_parts = tuple(int(part) for part in normalize_version(right).split("."))
    return (left_parts > right_parts) - (left_parts < right_parts)


@dataclass(frozen=True, slots=True)
class UpdateCommand:
    """由 Web 应用提交给主机更新器的受约束命令。"""

    operation_id: str
    action: str
    expected_version: str
    requested_by: str
    created_at: float
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        """转换为持久化命令字典。"""

        return asdict(self)


@dataclass(frozen=True, slots=True)
class UpdateOperation:
    """供前端轮询的更新操作状态。"""

    operation_id: str
    action: str
    state: str
    expected_version: str
    created_at: float
    updated_at: float
    message: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为 API 响应字典。"""

        return asdict(self)
