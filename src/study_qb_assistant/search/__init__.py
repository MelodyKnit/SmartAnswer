"""基于标准化题目记录的本地轻量级检索索引。

此模块提供 LocalQuestionIndex 类，支持在内存中对导入的标准 JSONL 题目记录进行
精确匹配和基于 n-gram 召回与 RapidFuzz 精排的模糊匹配检索。
"""

from __future__ import annotations

from pathlib import Path

from ..answer_reuse import record_should_be_indexable_by_reuse_policy
from ..auth import AuthError
from ..exporting import write_jsonl
from ..input_anomalies import normalize_image_urls
from ..models import CanonicalQuestionRecord, QueryResult, QuestionQuery
from .matching import MatchCandidate, QuestionMatcher
from .support import float_from_metadata, is_ai_record, read_jsonl_records


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
        self._matcher = QuestionMatcher(self._matchable_records())

    @classmethod
    def from_jsonl(cls, path: str | Path) -> "LocalQuestionIndex":
        """从本地的标准化 JSONL 文件加载数据并创建索引实例。

        Args:
            path: 本地 JSONL 文件的路径。

        Returns:
            LocalQuestionIndex: 初始化完成的检索索引实例。
        """
        resolved_path = Path(path)
        records = read_jsonl_records(resolved_path)
        return cls(tuple(records), source_path=str(resolved_path))

    @classmethod
    def from_jsonl_files(cls, paths: tuple[str | Path, ...]) -> "LocalQuestionIndex":
        """从多个标准化 JSONL 文件加载题库记录并创建统一索引。

        Args:
            paths: 一个或多个 JSONL 路径。不存在的路径会被跳过，便于 LLM 沉淀题库首次启动为空。

        Returns:
            LocalQuestionIndex: 合并后的统一检索索引。
        """
        records: list[CanonicalQuestionRecord] = []
        loaded_paths: list[str] = []
        for path in paths:
            resolved_path = Path(path)
            if not resolved_path.exists():
                continue
            records.extend(read_jsonl_records(resolved_path))
            loaded_paths.append(str(resolved_path))
        return cls(tuple(records), source_path=";".join(loaded_paths))

    def add_or_replace(self, record: CanonicalQuestionRecord) -> None:
        """向当前内存索引追加或替换一条题库记录。

        运行时 LLM 自动沉淀题会通过此入口立即参与后续查询，无需重启服务。
        """
        records = [
            existing for existing in self.records if existing.question_id != record.question_id
        ]
        records.append(record)
        self.records = tuple(records)
        self._rebuild_match_index()

    def remove(self, question_id: str) -> None:
        """从当前内存索引中移除一条题库记录。"""

        self.records = tuple(
            record for record in self.records if record.question_id != question_id
        )
        self._rebuild_match_index()

    def replace_records(self, records: tuple[CanonicalQuestionRecord, ...]) -> None:
        """用一批可信记录整体重建当前内存索引。"""

        self.records = records
        self._rebuild_match_index()

    def update_record(self, question_id: str, values: dict[str, object]) -> CanonicalQuestionRecord:
        """更新题库记录，并在源为 JSONL 文件时同步持久化。"""
        updated: CanonicalQuestionRecord | None = None
        next_records: list[CanonicalQuestionRecord] = []
        for record in self.records:
            if record.question_id != question_id:
                next_records.append(record)
                continue
            payload = record.to_dict()
            for key in {
                "title_raw",
                "question_type",
                "answer_raw",
                "explanation",
                "subject",
                "chapter",
                "source_name",
                "source_url",
                "source_license",
                "source_split",
                "source_record_path",
                "passage",
            }:
                if key in values:
                    payload[key] = values[key]
            if "options_raw" in values:
                raw_options = values["options_raw"]
                payload["options_raw"] = (
                    tuple(str(item) for item in raw_options)
                    if isinstance(raw_options, (list, tuple, set))
                    else ()
                )
            if "tags" in values:
                raw_tags = values["tags"]
                payload["tags"] = (
                    tuple(str(item) for item in raw_tags)
                    if isinstance(raw_tags, (list, tuple, set))
                    else ()
                )
            if "metadata" in values and isinstance(values["metadata"], dict):
                payload["metadata"] = {str(k): str(v) for k, v in values["metadata"].items()}
            updated = CanonicalQuestionRecord.from_dict(payload)
            next_records.append(updated)
        if updated is None:
            raise AuthError("QUESTION_NOT_FOUND", "题目不存在", http_status=404)
        self.records = tuple(next_records)
        self._rebuild_match_index()
        if self.source_path and Path(self.source_path).suffix.lower() == ".jsonl":
            write_jsonl(self.records, self.source_path)
        return updated

    def _rebuild_match_index(self) -> None:
        """重建本地高稳匹配索引。"""
        self._matcher = QuestionMatcher(self._matchable_records())

    def _matchable_records(self) -> tuple[CanonicalQuestionRecord, ...]:
        """返回允许参与自动命中的题库记录。"""

        return tuple(
            record
            for record in self.records
            if not normalize_image_urls((record.title_raw,))
            and record_should_be_indexable_by_reuse_policy(record)
        )

    def status(self) -> dict:
        """获取关于已加载索引的非敏感统计和运行时诊断细节。

        Returns:
            dict: 包含提供商名称、记录总数、源文件路径、涉及的数据源名称及授权许可列表。
        """
        sources = sorted({record.source_name for record in self.records})
        licenses = sorted(
            {record.source_license for record in self.records if record.source_license}
        )
        return {
            "provider": "local-normalized-jsonl",
            "record_count": len(self.records),
            "source_path": self.source_path,
            "source_names": sources,
            "source_licenses": licenses,
            "match_index": self._matcher.status(),
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

        exact_candidate = self._matcher.exact_match(query)
        if exact_candidate is not None:
            return self._result_from_match(exact_candidate, query, resolution_mode="exact_match")

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

        fuzzy_candidate = self._matcher.fuzzy_match(query)
        if fuzzy_candidate is None:
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
                error_message="no trusted local match found",
                debug={"match_stage": "not_found"},
            )

        return self._result_from_match(fuzzy_candidate, query, resolution_mode="fuzzy_match")

    def _result_from_match(
        self,
        candidate: MatchCandidate,
        query: QuestionQuery,
        resolution_mode: str,
    ) -> QueryResult:
        """从匹配候选生成标准查询结果。"""
        return self._result_from_record(
            candidate.record,
            query,
            confidence=candidate.confidence,
            resolution_mode=resolution_mode,
            debug={
                "match_stage": candidate.match_stage,
                "title_score": f"{candidate.title_score:.4f}",
                "option_score": f"{candidate.option_score:.4f}",
                "candidate_count": str(candidate.candidate_count),
                "top_gap": f"{candidate.top_gap:.4f}",
            },
        )

    def _result_from_record(
        self,
        record: CanonicalQuestionRecord,
        query: QuestionQuery,
        confidence: float,
        resolution_mode: str,
        debug: dict[str, str] | None = None,
    ) -> QueryResult:
        """从匹配成功的 CanonicalQuestionRecord 结构体生成标准 QueryResult。"""
        answer_text = self._answer_text(record)
        ai_generated_record = is_ai_record(record)
        if ai_generated_record and record.metadata.get("ai_status") == "trusted":
            resolution_mode = "ai_cache"
            confidence = float_from_metadata(record.metadata.get("ai_confidence"), confidence)
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
                    "source_type": (
                        "ai_generated_question_bank" if ai_generated_record else "qa_record"
                    ),
                    "source_id": record.question_id,
                    "source_url": record.source_url,
                    "source_license": record.source_license,
                    "score": confidence,
                },
            ),
            debug=debug or {},
        )

    def _answer_text(self, record: CanonicalQuestionRecord) -> str | None:
        """获取记录中答案标签对应的选项实际文本（例如标签 "A" 映射为 "对" 或 具体选项内容）。"""
        if record.metadata.get("ai_answer_text"):
            return record.metadata["ai_answer_text"]
        if not record.answer_raw:
            return None
        choice_map = record.as_choice_map()
        return choice_map.get(record.answer_raw, record.answer_raw)
