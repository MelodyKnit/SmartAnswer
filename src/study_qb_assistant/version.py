"""应用构建版本信息。

生产镜像由发布流水线注入版本与提交号；本地源码运行统一显示为 ``dev``，
避免再维护与 ``pyproject.toml`` 容易漂移的第二份版本常量。
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
BUILD_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")


@dataclass(frozen=True, slots=True)
class BuildInfo:
    """描述当前运行构建的公开版本信息。"""

    version: str
    build_sha: str
    build_type: str

    def to_dict(self) -> dict[str, str]:
        """转换为 API 可直接返回的字典。"""

        return asdict(self)


def current_build_info() -> BuildInfo:
    """从镜像构建环境读取版本信息，并对异常值做安全降级。"""

    raw_version = os.getenv("STQB_APP_VERSION", "").strip().removeprefix("v")
    version = raw_version if VERSION_RE.fullmatch(raw_version) else "dev"
    raw_sha = os.getenv("STQB_BUILD_SHA", "").strip().lower()
    build_sha = raw_sha if BUILD_SHA_RE.fullmatch(raw_sha) else "unknown"
    return BuildInfo(
        version=version,
        build_sha=build_sha,
        build_type="release" if version != "dev" else "source",
    )


BUILD_INFO = current_build_info()
