"""OCS 风格的源配置辅助程序。

该模块不再维护独立硬编码配置，而是复用平台导入脚本模板目录中的默认 OCS 模板，
确保 `/configs/ocs-local-study-bank.json`、用户“复制导入脚本”和后台模板预览共用同一来源。
"""

from __future__ import annotations

from ...platform.import_script_catalog import get_import_script_template, render_import_script


def build_ocs_config(base_url: str) -> list[dict]:
    """为本地服务构建 OCS 风格的源配置信息。

    参数:
        base_url: 本地服务的基准 URL 地址（例如 "http://localhost:8000"）。

    返回:
        list[dict]: 包含 OCS 风格源配置字典的列表。
    """
    template = get_import_script_template()
    rendered = render_import_script(template, base_url=base_url)
    return list(rendered["ocs_config"])
