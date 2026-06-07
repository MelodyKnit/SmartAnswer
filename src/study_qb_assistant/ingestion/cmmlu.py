"""CMMLU 数据集解析与读取器。

该模块负责读取 CMMLU 格式的 CSV 数据，解析出题目、A/B/C/D 四个选项、标准答案和相关元数据，
并将其规范化为内部统一的 CanonicalQuestionRecord 格式。
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterator

from ..models import CanonicalQuestionRecord
from ._shared import tupled_options

# CMMLU 数据集的开源托管仓库 URL
CMMLU_SOURCE_URL = "https://github.com/haonan-li/CMMLU"
# 许可协议说明
CMMLU_LICENSE = "CC BY-NC-SA 4.0"


def iter_cmmlu_records(path: str | Path) -> Iterator[CanonicalQuestionRecord]:
    """从 CMMLU 的 CSV 文件中读取并产出规范化的题目记录。

    该函数会读取带有 UTF-8 BOM 头的 CSV 文件，提取各列内容，
    并为每道题生成全局唯一的 `question_id`。

    参数:
        path: CMMLU 数据集 CSV 文件的路径。

    产出:
        Iterator[CanonicalQuestionRecord]: 规范化的题目记录迭代器。
    """

    source_path = Path(path)
    # 使用文件名（无后缀）作为题目所属的学科主题 (e.g. computer_security)
    subject = source_path.stem
    # 使用文件所在的父目录名作为数据集切分（如 test, dev）
    split = source_path.parent.name

    # 使用 utf-8-sig 以兼容并自动去除 Windows 等平台可能带有的 BOM 头
    with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_index, row in enumerate(reader):
            # 拼接生成全局唯一的题目 ID 标识
            question_id = f"cmmlu:{subject}:{split}:{row_index}"
            yield CanonicalQuestionRecord(
                question_id=question_id,
                title_raw=row["Question"].strip(),
                question_type="single",  # CMMLU 数据集均为单项选择题
                # 提取标准 A/B/C/D 四个选项并进行标准化去空处理
                options_raw=tupled_options((row.get("A"), row.get("B"), row.get("C"), row.get("D"))),
                answer_raw=(row.get("Answer") or "").strip() or None,
                explanation=None,  # CMMLU 不带解析说明，设为 None
                subject=subject,
                chapter=None,
                tags=("cmmlu", subject),
                source_name="CMMLU",
                source_url=CMMLU_SOURCE_URL,
                source_license=CMMLU_LICENSE,
                source_split=split,
                source_record_path=str(source_path),
            )
