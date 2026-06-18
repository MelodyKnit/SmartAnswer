"""数据导入、导出与本地检索通用的文本标准化工具函数。

本模块提供对题干和选项文本进行标准化的辅助函数，以消除空白字符、括号前缀等噪声对匹配结果的影响。
"""

from __future__ import annotations

import re

# 用于匹配并替换所有连续空白字符的正则表达式
_WHITESPACE_RE = re.compile(r"\s+")
# 用于匹配并滤除选项开头的字母前缀（如 "A."，"[B]"，"(C)"，"D、" 等）的正则表达式
_CHOICE_PREFIX_RE = re.compile(r"^\s*[\(\[]?([A-Fa-f])[\)\].、:：]\s*")


def normalize_text(value: str | None) -> str:
    """去除文本中所有空白字符并转换为小写，用于生成紧凑一致的题目比对键。

    Args:
        value: 原始字符串文本。

    Returns:
        str: 标准化后的紧凑小写字符串。
    """
    if value is None:
        return ""
    # 替换所有空格、制表符、换行等空白字符
    compact = _WHITESPACE_RE.sub("", value)
    return compact.casefold()


def normalize_option(value: str | None) -> str:
    """标准化单个选项文本，支持自动容忍并滤除选项字母前缀。

    Args:
        value: 原始选项文本。

    Returns:
        str: 移除前缀并标准化处理后的字符串。
    """
    if value is None:
        return ""
    # 移除选项开头的 "A."、"(B)" 等标识前缀，然后再进行常规文本标准化
    stripped = _CHOICE_PREFIX_RE.sub("", value.strip())
    return normalize_text(stripped)


def normalize_options(values: tuple[str, ...]) -> tuple[str, ...]:
    """标准化选项元组，供感知选项的模糊/精确题库检索匹配使用。

    自动过滤掉标准化后为空的干扰选项。

    Args:
        values: 原始选项文本元组。

    Returns:
        tuple[str, ...]: 标准化后的选项元组。
    """
    return tuple(normalize_option(value) for value in values if normalize_option(value))
