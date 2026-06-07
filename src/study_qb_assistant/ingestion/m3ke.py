"""M3KE 数据集解析与读取器。

该模块负责读取 M3KE 格式 of JSONL 数据，解析出题目、选项、标准答案及元数据，
并将其规范化为内部统一的 CanonicalQuestionRecord 格式。
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from ..models import CanonicalQuestionRecord
from ._shared import load_json_lines, tupled_options

# M3KE 数据集的开源托管仓库 URL
M3KE_SOURCE_URL = "https://github.com/tjunlp-lab/M3KE"
# 许可协议说明
M3KE_LICENSE = "unknown-needs-confirmation"


def iter_m3ke_records(path: str | Path) -> Iterator[CanonicalQuestionRecord]:
    """从 M3KE 的 JSONL 文件中读取并产出规范化的题目记录。

    该函数会解析文件名（如 学科-门类-等级.jsonl 结构）以提取学科、知识门类及等级，
    并为每道题目自动生成全局唯一的 `question_id`。

    参数:
        path: M3KE 数据集 JSONL 文件的路径。

    产出:
        Iterator[CanonicalQuestionRecord]: 规范化的题目记录迭代器。
    """

    source_path = Path(path)
    # 获取数据集划分（例如 train, dev, test）
    split = source_path.parent.name
    # 通过文件名解析出学科(subject)、学科大类(discipline)、学段级别(level)
    subject, discipline, level = _parse_m3ke_stem(source_path.stem)

    for row in load_json_lines(source_path):
        # 拼接生成全局唯一的题目 ID 标识
        question_id = f"m3ke:{subject}:{split}:{row['id']}"
        yield CanonicalQuestionRecord(
            question_id=question_id,
            title_raw=row["question"].strip(),
            question_type="single",  # M3KE 主要包含单项选择题
            # 提取标准的 A/B/C/D 四个选项并格式化
            options_raw=tupled_options((row.get("A"), row.get("B"), row.get("C"), row.get("D"))),
            answer_raw=(row.get("answer") or "").strip() or None,
            explanation=None,  # M3KE 数据集通常不提供题目的详细解析文字，设为 None
            subject=subject,
            chapter=None,
            tags=("m3ke", discipline, level),
            source_name="M3KE",
            source_url=M3KE_SOURCE_URL,
            source_license=M3KE_LICENSE,
            source_split=split,
            source_record_path=str(source_path),
        )


def _parse_m3ke_stem(stem: str) -> tuple[str, str, str]:
    """将文件名切分为学科、学科大类与难度/级别三部分。

    例如将 "中国历史-人文-中考" 拆分为 ("中国历史", "人文", "中考")。

    参数:
        stem: 文件名（不含后缀，如 "subject-discipline-level"）。

    返回:
        tuple[str, str, str]: (学科, 学科大类, 等级) 组成的三元组。
    """

    # 从右往左按 "-" 分隔两次，得到学科名、学科分类和学段等级
    subject, discipline, level = stem.rsplit("-", 2)
    return subject, discipline, level
