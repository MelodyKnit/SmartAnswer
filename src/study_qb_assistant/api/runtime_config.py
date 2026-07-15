"""系统配置到当前进程环境的同步。"""

from __future__ import annotations

import os

from ..platform.settings import SettingsService


def apply_system_config_to_process(settings: SettingsService) -> None:
    """把系统配置写回当前进程环境变量。"""
    for env_key, value in settings.runtime_env().items():
        os.environ[env_key] = value
