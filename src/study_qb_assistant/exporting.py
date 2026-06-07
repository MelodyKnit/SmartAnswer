"""将标准化的题目记录导出为项目所属的 JSONL 文件。

本模块提供将 CanonicalQuestionRecord 结构化数据写入本地 JSONL 文件的功能，
并在此过程中记录数据量与数据来源，并支持输出元数据清单文件（manifest）。
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

from .models import CanonicalQuestionRecord


@dataclass(slots=True)
class ExportSummary:
    """标准化数据导出操作的摘要统计信息。

    Attributes:
        output_path: 导出的输出文件路径。
        record_count: 导出的题目记录总数。
        source_counts: 各个数据源及其对应导出数量的映射字典。
    """

    output_path: str
    record_count: int
    source_counts: dict[str, int]


def write_jsonl(records: Iterable[CanonicalQuestionRecord], output_path: str | Path) -> ExportSummary:
    """将标准题目记录写入本地 JSONL 文件并返回导出摘要统计。

    每一行都是一条独立的、按字段排序的 JSON 对象。如果目标文件夹不存在，将自动创建。

    Args:
        records: 包含 CanonicalQuestionRecord 对象的迭代器。
        output_path: 导出的 JSONL 文件保存路径。

    Returns:
        ExportSummary: 导出的统计摘要对象。
    """
    path = Path(output_path)
    # 确保输出文件所在的上级目录存在
    path.parent.mkdir(parents=True, exist_ok=True)
    record_count = 0
    source_counts: dict[str, int] = {}

    # 以 UTF-8 编码以及标准换行符打开文件，开始逐行写入
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            record_count += 1
            # 统计各个数据源的记录条数
            source_counts[record.source_name] = source_counts.get(record.source_name, 0) + 1
            # 将记录序列化为不转义非 ASCII 字符（保持中文可读）且键排序的 JSON 字符串
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True))
            handle.write("\n")

    return ExportSummary(str(path), record_count, source_counts)


def write_export_manifest(summary: ExportSummary, manifest_path: str | Path) -> None:
    """在导出的标准化数据旁持久化保存一份小型的元数据清单（manifest）。

    通常用于自动化流水线确认数据导出的完整性。

    Args:
        summary: 导出的统计摘要对象。
        manifest_path: 清单 JSON 文件的保存路径。
    """
    path = Path(manifest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(summary)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        # 写入格式化且排序好的 JSON 清单文件
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")

