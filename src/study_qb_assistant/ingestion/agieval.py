"""AGIEval 数据集解析与读取器。

该模块负责读取 AGIEval 格式的 JSONL 数据，提取题目、选项、标准答案和相关元数据，
并将其规范化为内部统一的 CanonicalQuestionRecord 格式。
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from ..models import CanonicalQuestionRecord
from ._shared import load_json_lines, tupled_options

# AGIEval 数据集的开源托管仓库 URL
AGIEVAL_SOURCE_URL = "https://github.com/ruixiangcui/AGIEval"
# 许可协议说明，遵循原始数据集的相应许可
AGIEVAL_LICENSE = "follow-original-dataset-licenses"


def iter_agieval_records(path: str | Path) -> Iterator[CanonicalQuestionRecord]:
    """从 AGIEval 的 JSONL 文件中读取并产出规范化的题目记录。

    该函数会解析文件名作为学科(subject)，其父目录名作为数据集拆分(split，如 train, test)，
    并为每道题目自动生成全局唯一的 `question_id`。

    参数:
        path: AGIEval 数据集文件的文件路径 (JSONL 格式)。

    产出:
        Iterator[CanonicalQuestionRecord]: 规范化的题目记录迭代器。
    """

    source_path = Path(path)
    # 使用文件名（无后缀）作为题目所属的学科主题
    subject = source_path.stem
    # 使用文件所在的父目录名作为数据集切分（如 dev, test）
    split = source_path.parent.name

    for row_index, row in enumerate(load_json_lines(source_path)):
        metadata: dict[str, str] = {}
        other = row.get("other")
        # 如果存在 "other" 字段，将其键值对作为元数据存入
        if isinstance(other, dict):
            metadata.update({str(key): str(value) for key, value in other.items()})

        # 归一化提取的答案：AGIEval 的答案字段可能为 "label" 或 "answer"
        answer_raw = _normalize_answer(row.get("label") or row.get("answer"))
        # 若包含 "options" 字段，则视其为单选题（single），否则标记为未知（unknown）
        question_type = "single" if row.get("options") else "unknown"
        # 拼接生成全局唯一的题目 ID 标识
        question_id = f"agieval:{subject}:{split}:{row_index}"

        yield CanonicalQuestionRecord(
            question_id=question_id,
            title_raw=row["question"].strip(),
            question_type=question_type,
            options_raw=tupled_options(row.get("options") or ()),
            answer_raw=answer_raw,
            explanation=None,  # AGIEval 通常没有预置的详细文字解析，设置为 None
            subject=subject,
            chapter=None,
            tags=("agieval", split),
            source_name="AGIEval",
            source_url=AGIEVAL_SOURCE_URL,
            source_license=AGIEVAL_LICENSE,
            source_split=split,
            source_record_path=str(source_path),
            passage=(row.get("passage") or None),  # 若存在阅读理解类材料片段，则一并保存
            metadata=metadata,
        )


def _normalize_answer(value: object) -> str | None:
    """标准化题目答案的格式。

    若答案为列表类型，则去除空格并用 "#" 号拼接；
    若为普通单字符串或数字，则直接转换为去除空格后的字符串。
    """
    if value is None:
        return None
    if isinstance(value, list):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return "#".join(parts) or None
    text = str(value).strip()
    return text or None
