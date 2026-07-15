"""本地原始数据源目录的数据集目录（Catalog）辅助程序。

该模块负责扫描本地项目中的原始数据集文件（如 CMMLU、M3KE、AGIEval 等），
并对外提供统一的题目数据迭代接口。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from study_qb_assistant.questions.models import CanonicalQuestionRecord
from .agieval import iter_agieval_records
from .cmmlu import iter_cmmlu_records
from .m3ke import iter_m3ke_records


def iter_source_records(project_root: str | Path, source: str) -> Iterator[CanonicalQuestionRecord]:
    """生成并迭代指定数据源在本地所有可用的题目记录。

    参数:
        project_root: 项目的根目录路径。
        source: 数据源标识符（如 "cmmlu", "m3ke", "agieval", "agieval-mcq", "verified", "all"）。

    返回:
        Iterator[CanonicalQuestionRecord]: 对应数据源中所有标准题目的迭代器。

    异常:
        ValueError: 当传入不支持的数据源标识符时抛出。
    """

    root = Path(project_root)
    # 根据数据源名称匹配相应的子目录扫描器
    match source:
        case "cmmlu":
            yield from _iter_cmmlu(root)
        case "m3ke":
            yield from _iter_m3ke(root)
        case "agieval":
            yield from _iter_agieval(root)
        case "agieval-mcq":
            # 仅提取 AGIEval 中的选择题 (Multiple Choice Questions)
            yield from _iter_agieval_mcq(root)
        case "verified":
            # 返回已被人工或评测验证的高质量子集（如 CMMLU 和 AGIEval-MCQ 的合集）
            yield from _iter_cmmlu(root)
            yield from _iter_agieval_mcq(root)
        case "all":
            # 返回所有支持的数据集之和
            yield from _iter_cmmlu(root)
            yield from _iter_m3ke(root)
            yield from _iter_agieval(root)
        case _:
            raise ValueError(f"unsupported source: {source}")


def _iter_cmmlu(root: Path) -> Iterator[CanonicalQuestionRecord]:
    """遍历本地 cmmlu-upstream 目录下的所有 CSV 文件，并解析出题目记录。"""
    for path in sorted((root / "data" / "raw" / "cmmlu-upstream" / "data").glob("*/*.csv")):
        yield from iter_cmmlu_records(path)


def _iter_m3ke(root: Path) -> Iterator[CanonicalQuestionRecord]:
    """遍历本地 m3ke-upstream 目录下的所有 JSONL 文件，并解析出题目记录。"""
    for path in sorted((root / "data" / "raw" / "m3ke-upstream" / "data").glob("*/*.jsonl")):
        yield from iter_m3ke_records(path)


def _iter_agieval(root: Path) -> Iterator[CanonicalQuestionRecord]:
    """遍历本地 agieval-upstream 目录下的所有 JSONL 文件，并解析出题目记录。"""
    base = root / "data" / "raw" / "agieval-upstream" / "data" / "v1_1"
    for path in sorted(base.glob("*.jsonl")):
        yield from iter_agieval_records(path)


def _iter_agieval_mcq(root: Path) -> Iterator[CanonicalQuestionRecord]:
    """从 AGIEval 题目中过滤出仅包含单选题且有明确标准答案的记录。"""
    for record in _iter_agieval(root):
        if record.question_type == "single" and record.answer_raw:
            yield record
