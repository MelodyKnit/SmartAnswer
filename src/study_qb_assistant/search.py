"""基于标准化题目记录的本地轻量级检索索引。

此模块提供 LocalQuestionIndex 类，支持在内存中对导入的标准 JSONL 题目记录进行
精确匹配和基于编辑距离与选项重合度的模糊匹配检索。
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path

from .models import CanonicalQuestionRecord, QueryResult, QuestionQuery
from .normalization import normalize_options, normalize_text


class LocalQuestionIndex:
    """在内存中对标准化 JSONL 题目记录进行精确和模糊检索的本地索引。

    在初始化时对所有题目的标准化题干建立哈希映射，以支持高效的精确查找。
    """

    def __init__(
        self,
        records: tuple[CanonicalQuestionRecord, ...],
        *,
        source_path: str | None = None,
    ) -> None:
        """初始化内存题目检索索引。

        Args:
            records: 标准化题目记录的元组。
            source_path: 加载的数据源文件路径（可选，主要用于 status 展示）。
        """
        self.records = records
        self.source_path = source_path
        # 初始化精确匹配哈希表，键为标准化后的题干文本，值为拥有相同标准化题干的记录列表
        self._exact: dict[str, list[CanonicalQuestionRecord]] = {}
        for record in records:
            key = normalize_text(record.title_raw)
            self._exact.setdefault(key, []).append(record)

    @classmethod
    def from_jsonl(cls, path: str | Path) -> "LocalQuestionIndex":
        """从本地的标准化 JSONL 文件加载数据并创建索引实例。

        Args:
            path: 本地 JSONL 文件的路径。

        Returns:
            LocalQuestionIndex: 初始化完成的检索索引实例。
        """
        resolved_path = Path(path)
        records = _read_jsonl_records(resolved_path)
        return cls(tuple(records), source_path=str(resolved_path))

    @classmethod
    def from_jsonl_files(cls, paths: tuple[str | Path, ...]) -> "LocalQuestionIndex":
        """从多个标准化 JSONL 文件加载题库记录并创建统一索引。

        Args:
            paths: 一个或多个 JSONL 路径。不存在的路径会被跳过，便于 AI 沉淀题库首次启动为空。

        Returns:
            LocalQuestionIndex: 合并后的统一检索索引。
        """
        records: list[CanonicalQuestionRecord] = []
        loaded_paths: list[str] = []
        for path in paths:
            resolved_path = Path(path)
            if not resolved_path.exists():
                continue
            records.extend(_read_jsonl_records(resolved_path))
            loaded_paths.append(str(resolved_path))
        return cls(tuple(records), source_path=";".join(loaded_paths))

    def add_or_replace(self, record: CanonicalQuestionRecord) -> None:
        """向当前内存索引追加或替换一条题库记录。

        运行时 AI 自动沉淀题会通过此入口立即参与后续查询，无需重启服务。
        """
        records = [existing for existing in self.records if existing.question_id != record.question_id]
        records.append(record)
        self.records = tuple(records)
        self._rebuild_exact_index()

    def _rebuild_exact_index(self) -> None:
        """重建标准化题干的精确匹配索引。"""
        self._exact = {}
        for record in self.records:
            key = normalize_text(record.title_raw)
            self._exact.setdefault(key, []).append(record)

    def status(self) -> dict:
        """获取关于已加载索引的非敏感统计和运行时诊断细节。

        Returns:
            dict: 包含提供商名称、记录总数、源文件路径、涉及的数据源名称及授权许可列表。
        """
        sources = sorted({record.source_name for record in self.records})
        licenses = sorted({record.source_license for record in self.records if record.source_license})
        return {
            "provider": "local-normalized-jsonl",
            "record_count": len(self.records),
            "source_path": self.source_path,
            "source_names": sources,
            "source_licenses": licenses,
        }

    def query(self, query: QuestionQuery, *, allow_fuzzy: bool = True) -> QueryResult:
        """根据标准查询，在本地索引中检索最匹配的答案候选。

        Args:
            query: 查询结构体。
            allow_fuzzy: 在精确匹配未命中时，是否允许降级为全局模糊匹配，默认开启。

        Returns:
            QueryResult: 带有置信度、决议模式及来源标记的检索结果。
        """
        # 题干文本为空时直接拦截
        if not query.title.strip():
            return QueryResult(
                ok=False,
                query=query,
                candidate_answer=None,
                answer_text=None,
                explanation=None,
                confidence=0.0,
                resolution_mode="invalid_request",
                review_required=True,
                error_code="INVALID_REQUEST",
                error_message="title is required",
            )

        query_key = normalize_text(query.title)
        # 优先执行 O(1) 的精确查找
        exact_candidates = self._exact.get(query_key) or []
        if exact_candidates:
            exact_candidates = [
                record
                for record in exact_candidates
                if not _is_ai_record(record) or _record_options_match(record, query)
            ]
        if exact_candidates:
            # 如果命中了多个同题干题目（比如选项不同），基于选项匹配度进行优胜排序
            record = self._rank_candidates(exact_candidates, query)[0]
            return self._result_from_record(record, query, confidence=0.99, resolution_mode="exact_match")

        # 若精确查找未命中且不允许模糊匹配，则直接返回未找到
        if not allow_fuzzy:
            return QueryResult(
                ok=False,
                query=query,
                candidate_answer=None,
                answer_text=None,
                explanation=None,
                confidence=0.0,
                resolution_mode="not_found",
                review_required=True,
                error_code="NOT_FOUND",
                error_message="no trusted exact local match found",
            )

        # 降级方案：遍历索引中所有记录进行相似度评分（模糊查找）
        best_record: CanonicalQuestionRecord | None = None
        best_score = 0.0
        for record in self.records:
            # AI 自动沉淀题依赖具体选项顺序，不能通过相似题干模糊复用。
            if _is_ai_record(record):
                continue
            score = self._score_record(record, query)
            if score > best_score:
                best_record = record
                best_score = score

        # 相似度阈值设定为 0.72，低于该分值则认为无法建立足够信任，返回未找到
        if best_record is None or best_score < 0.72:
            return QueryResult(
                ok=False,
                query=query,
                candidate_answer=None,
                answer_text=None,
                explanation=None,
                confidence=best_score,
                resolution_mode="not_found",
                review_required=True,
                error_code="NOT_FOUND",
                error_message="no trusted local match found",
            )

        return self._result_from_record(
            best_record,
            query,
            confidence=round(best_score, 4),
            resolution_mode="fuzzy_match",
        )

    def _rank_candidates(
        self, records: list[CanonicalQuestionRecord], query: QuestionQuery
    ) -> list[CanonicalQuestionRecord]:
        """对多个候选记录按选项匹配度得分从高到低进行排序。"""
        return sorted(records, key=lambda record: self._option_score(record, query), reverse=True)

    def _score_record(self, record: CanonicalQuestionRecord, query: QuestionQuery) -> float:
        """为单条记录与查询条件计算综合匹配相似度评分。

        综合分值由题干的编辑距离相似度（比重 82%）与选项重合度得分（比重 18%）加权得出。
        """
        # 使用 SequenceMatcher 计算题干字符级别的匹配比率
        title_score = difflib.SequenceMatcher(
            None, normalize_text(record.title_raw), normalize_text(query.title)
        ).ratio()
        option_score = self._option_score(record, query)
        # 如果任何一方不包含选项信息，仅以题干相似度作为最终得分
        if option_score == 0:
            return title_score
        # 加权求和：82% 题干匹配度 + 18% 选项匹配度
        return (title_score * 0.82) + (option_score * 0.18)

    def _option_score(self, record: CanonicalQuestionRecord, query: QuestionQuery) -> float:
        """计算查询选项与记录选项的重合重度得分（交集大小除以并集大小，即 Jaccard 相似度）。"""
        query_options = set(normalize_options(query.options))
        record_options = set(normalize_options(record.options_raw))
        if not query_options or not record_options:
            return 0.0
        overlap = query_options & record_options
        return len(overlap) / max(len(query_options), len(record_options))

    def _result_from_record(
        self,
        record: CanonicalQuestionRecord,
        query: QuestionQuery,
        confidence: float,
        resolution_mode: str,
    ) -> QueryResult:
        """从匹配成功的 CanonicalQuestionRecord 结构体生成标准 QueryResult。"""
        answer_text = self._answer_text(record)
        is_ai_record = _is_ai_record(record)
        if is_ai_record and record.metadata.get("ai_status") == "trusted":
            resolution_mode = "ai_cache"
            confidence = _float_from_metadata(record.metadata.get("ai_confidence"), confidence)
        return QueryResult(
            ok=True,
            query=query,
            candidate_answer=record.answer_raw,
            answer_text=answer_text,
            explanation=record.explanation,
            confidence=confidence,
            resolution_mode=resolution_mode,
            # 置信度低于 0.9（如来自模糊匹配）时，标记需要人工审核
            review_required=confidence < 0.9,
            sources=(
                {
                    "source_name": record.source_name,
                    "source_type": "ai_generated_question_bank" if is_ai_record else "qa_record",
                    "source_id": record.question_id,
                    "source_url": record.source_url,
                    "source_license": record.source_license,
                    "score": confidence,
                },
            ),
        )

    def _answer_text(self, record: CanonicalQuestionRecord) -> str | None:
        """获取记录中答案标签对应的选项实际文本（例如标签 "A" 映射为 "对" 或 具体选项内容）。"""
        if record.metadata.get("ai_answer_text"):
            return record.metadata["ai_answer_text"]
        if not record.answer_raw:
            return None
        choice_map = record.as_choice_map()
        return choice_map.get(record.answer_raw, record.answer_raw)


def _read_jsonl_records(path: Path) -> list[CanonicalQuestionRecord]:
    """读取标准化 JSONL 题库记录。"""
    records: list[CanonicalQuestionRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(CanonicalQuestionRecord.from_dict(json.loads(line)))
    return records


def _float_from_metadata(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_ai_record(record: CanonicalQuestionRecord) -> bool:
    return record.source_name == "AIGenerated" or "ai_generated" in record.tags


def _record_options_match(record: CanonicalQuestionRecord, query: QuestionQuery) -> bool:
    """AI learned records are reusable only when their option set/order matches."""
    if not record.options_raw and not query.options:
        return True
    return normalize_options(record.options_raw) == normalize_options(query.options)
