"""数据导入模块的共享辅助程序。

该模块提供了文件加载、格式清理及数据规范化等通用辅助函数，供各个特定数据集导入模块使用。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator


def load_json_lines(path: str | Path) -> Iterator[dict]:
    """从每一行都是 JSON 字符串的文件 (JSONL) 中逐行读取并反序列化 JSON 对象。

    参数:
        path: JSONL 文件的路径。

    产出:
        Iterator[dict]: 逐行解析出的 JSON 字典。
    """

    source_path = Path(path)
    with source_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            # 过滤掉空行，防止 JSON 格式错误导致反序列化失败
            if not line:
                continue
            yield json.loads(line)


def tupled_options(values: Iterable[str | None]) -> tuple[str, ...]:
    """将选项的迭代序列标准化为紧凑且过滤掉空值的元组。

    参数:
        values: 原始选项字符串的迭代器/可迭代对象。

    返回:
        tuple[str, ...]: 清理首尾空格且去空后的选项元组。
    """

    # 去除首尾多余空白，并过滤掉空值或纯空格字符串
    return tuple(value.strip() for value in values if value and value.strip())
