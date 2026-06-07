"""OCS 风格的源配置辅助程序。

该模块用于为外部脚本或客户端生成连接到本地服务所需的 OCS 风格配置列表。
"""

from __future__ import annotations


def build_ocs_config(base_url: str) -> list[dict]:
    """为本地服务构建 OCS 风格的源配置信息。

    参数:
        base_url: 本地服务的基准 URL 地址（例如 "http://localhost:8000"）。

    返回:
        list[dict]: 包含 OCS 风格源配置字典的列表。
    """

    # 去除末尾的斜杠，以防拼接时出现双斜杠
    normalized_base = base_url.rstrip("/")
    return [
        {
            "name": "Local Study Question Bank",  # 题库源名称
            "homepage": f"{normalized_base}/healthz",  # 题库源主页，用于健康检查
            "url": f"{normalized_base}/ocs/query",  # 查询接口 URL
            "method": "get",  # 请求方式
            "type": "GM_xmlhttpRequest",  # 跨域请求类型，通常用于用户脚本 (Tampermonkey 等)
            "contentType": "json",  # 响应内容格式
            # 请求参数模板，${title}、${options} 和 ${type} 会被客户端/脚本引擎动态替换
            "data": {
                "title": "${title}",
                "options": "${options}",
                "type": "${type}",
            },
            # 客户端处理器脚本，用于解析服务响应：若成功则返回 [题目, 答案]，否则返回错误提示
            "handler": (
                "return (res)=>res.code === 0 ? "
                "[res.data.question, res.data.answer] "
                ": [res.message || (res.data && res.data.question) || '未找到答案', undefined]"
            ),
        }
    ]
