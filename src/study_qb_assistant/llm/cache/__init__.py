"""LLM 自动沉淀题库服务。

该模块保留“多次一致确认后才复用”的状态机，但把记录模型和辅助判断拆到独立文件中，
主文件只负责缓存状态机、持久化协调和对外接口。
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

from .records import CachedLlmAnswer
from .support import (
    answer_shape_is_valid,
    cache_record_key,
    cache_candidate_for_answer,
    canonical_candidate_from_payload,
    float_value,
    int_value,
    is_cacheable_model_answer,
    optional_string,
)
from study_qb_assistant.answering.reuse import record_should_be_indexable_by_reuse_policy, decide_answer_reuse
from study_qb_assistant.media.inputs import normalize_image_urls
from study_qb_assistant.questions.models import CanonicalQuestionRecord, ModelAnswer, QuestionQuery
from study_qb_assistant.questions.normalization import normalize_options, normalize_text
from study_qb_assistant.questions.labels import canonicalize_label_answer
from ...logger import log_event


STATE_COMPACTION_BYTES = 64 * 1024 * 1024
STATE_COMPACTION_MIN_RECORDS = 1000


class LlmAnswerCache:
    """LLM 自动沉淀题库管理器。"""

    def __init__(
        self,
        path: str | Path,
        *,
        state_path: str | Path | None = None,
        min_confidence: float = 0.95,
        min_confirmations: int = 2,
        legacy_paths: tuple[str | Path, ...] = (),
    ) -> None:
        """初始化 LLM 自动沉淀题库管理器。

        Args:
            path: LLM 自动沉淀题库 JSONL 存储路径。
            min_confidence: 允许沉淀的最低置信度阈值。
            min_confirmations: 晋升为 `trusted` 所需的一致确认次数。
            legacy_paths: 旧版 JSON 缓存路径集合，用于迁移。
        """
        self.path = Path(path)
        self.state_path = Path(state_path) if state_path is not None else None
        self.min_confidence = min(max(min_confidence, 0.0), 1.0)
        self.min_confirmations = max(1, min_confirmations)
        self.legacy_paths = tuple(Path(value) for value in legacy_paths)
        self._lock = Lock()
        self._entries: dict[str, CachedLlmAnswer] = {}
        self._state_record_count = 0
        self._compaction_scheduled = False
        self._compaction_executor = (
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="llm-cache-compact")
            if self.state_path is not None
            else None
        )
        self.load_entries()

    def get_trusted(self, query: QuestionQuery) -> CachedLlmAnswer | None:
        """获取匹配该查询且状态为受信任的缓存答案。"""
        if cache_query_has_image_context(query):
            return None
        key = cache_key(query)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry.status != "trusted":
                return None
            if not decide_answer_reuse(
                query,
                answer_text=entry.answer_text,
                candidate_answer=entry.candidate_answer,
            ).reusable:
                return None
            if not answer_shape_is_valid(query, entry.candidate_answer):
                return None
            return entry

    def record_model_answer(
        self,
        query: QuestionQuery,
        answer: ModelAnswer,
        *,
        provider_name: str,
        force_trusted: bool = False,
    ) -> CachedLlmAnswer | None:
        """记录新的模型答案，并在满足条件时提升其状态。"""
        if cache_query_has_image_context(query):
            return None
        if not is_cacheable_model_answer(query, answer, self.min_confidence, answer_shape_is_valid):
            return None

        now = time.time()
        key = cache_key(query)
        candidate = cache_candidate_for_answer(query, answer)
        with self._lock:
            existing = self._entries.get(key)
            if existing is None:
                entry = CachedLlmAnswer(
                    key=key,
                    title=query.title,
                    question_type=query.question_type,
                    options=query.options,
                    candidate_answer=candidate,
                    answer_text=answer.answer_text,
                    explanation=answer.explanation,
                    confidence=min(max(answer.confidence, 0.0), 1.0),
                    confirmations=1,
                    conflicts=0,
                    status=(
                        "trusted"
                        if force_trusted or self.min_confirmations <= 1
                        else "pending"
                    ),
                    provider_name=provider_name,
                    created_at=now,
                    updated_at=now,
                )
                self._entries[key] = entry
                self._persist_entry(entry)
                return entry

            existing_candidate = (
                canonicalize_label_answer(query, existing.candidate_answer)
                or existing.candidate_answer
            )
            if normalize_text(existing_candidate) != normalize_text(candidate):
                existing.conflicts += 1
                existing.status = "conflict"
                existing.updated_at = now
                self._persist_entry(existing)
                return existing

            existing.confirmations += 1
            existing.answer_text = answer.answer_text or existing.answer_text
            existing.explanation = answer.explanation or existing.explanation
            existing.confidence = max(existing.confidence, min(max(answer.confidence, 0.0), 1.0))
            existing.provider_name = provider_name
            existing.updated_at = now
            if (
                existing.conflicts == 0
                and (force_trusted or existing.confirmations >= self.min_confirmations)
            ):
                existing.status = "trusted"
            self._persist_entry(existing)
            return existing

    def status(self) -> dict:
        """获取缓存统计信息。"""
        with self._lock:
            statuses: dict[str, int] = {}
            for entry in self._entries.values():
                statuses[entry.status] = statuses.get(entry.status, 0) + 1
            return {
                "enabled": True,
                "path": str(self.path),
                "entry_count": len(self._entries),
                "statuses": statuses,
                "min_confidence": self.min_confidence,
                "min_confirmations": self.min_confirmations,
            }

    def load_entries(self) -> None:
        """从磁盘加载 LLM 沉淀记录，并兼容旧版 JSON 缓存迁移。"""
        loaded_legacy = False
        if self.path.exists():
            if self.path.suffix.lower() == ".jsonl":
                self.load_records_jsonl(self.path)
            else:
                self.load_legacy_json(self.path)
        for legacy_path in self.legacy_paths:
            if legacy_path.exists() and legacy_path.resolve() != self.path.resolve():
                loaded_legacy = self.load_legacy_json(legacy_path) or loaded_legacy
        if loaded_legacy and self.path.suffix.lower() == ".jsonl":
            self.save_entries()
        if self.state_path is not None:
            self.load_state_journal(self.state_path)

    def _persist_entry(self, entry: CachedLlmAnswer) -> None:
        """持久化一条缓存状态；生产模式追加小记录，兼容模式保留旧快照。"""

        if self.state_path is None:
            self.save_entries()
            return
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            with self.state_path.open("a", encoding="utf-8") as handle:
                json.dump(entry.to_dict(), handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
                handle.flush()
            self._state_record_count += 1
            self._schedule_compaction_if_needed()
        except OSError as exc:
            log_event(
                "llm_cache_persist_failed",
                {"error_type": type(exc).__name__},
            )

    def load_state_journal(self, path: Path) -> None:
        """读取增量状态文件，后出现的同键记录覆盖旧状态。"""

        if not path.exists():
            return
        offset = 0
        truncate_at: int | None = None
        append_separator = False
        malformed_lines = 0
        try:
            with path.open("rb") as handle:
                for raw_line in handle:
                    terminated = raw_line.endswith(b"\n")
                    line = raw_line.rstrip(b"\r\n")
                    if not line.strip():
                        if not terminated:
                            truncate_at = offset
                            break
                        offset += len(raw_line)
                        continue
                    try:
                        payload = json.loads(line.decode("utf-8"))
                        if not isinstance(payload, dict):
                            raise ValueError("cache journal record must be an object")
                        entry = CachedLlmAnswer.from_dict(
                            payload,
                            canonical_candidate_from_payload=canonical_candidate_from_payload,
                            optional_string=optional_string,
                            float_value=float_value,
                            int_value=int_value,
                        )
                    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                        malformed_lines += 1
                        if not terminated:
                            truncate_at = offset
                            break
                        offset += len(raw_line)
                        continue
                    self._entries[entry.key] = entry
                    self._state_record_count += 1
                    offset += len(raw_line)
                    if not terminated:
                        append_separator = True

            if truncate_at is not None:
                with path.open("r+b") as handle:
                    handle.truncate(truncate_at)
            elif append_separator:
                with path.open("ab") as handle:
                    handle.write(b"\n")
            if malformed_lines:
                log_event(
                    "llm_cache_journal_recovered",
                    {
                        "malformed_lines": malformed_lines,
                        "truncated_tail": truncate_at is not None,
                    },
                )
        except OSError as exc:
            log_event(
                "llm_cache_load_failed",
                {"error_type": type(exc).__name__},
            )

    def _schedule_compaction_if_needed(self) -> None:
        if self._compaction_executor is None or self._compaction_scheduled:
            return
        try:
            file_size = self.state_path.stat().st_size if self.state_path else 0
        except OSError:
            return
        if file_size < STATE_COMPACTION_BYTES and self._state_record_count < max(
            STATE_COMPACTION_MIN_RECORDS, len(self._entries) * 2
        ):
            return
        self._compaction_scheduled = True
        self._compaction_executor.submit(self._compact_state_journal)

    def _compact_state_journal(self) -> None:
        """在单线程后台任务中压缩增量状态，避免请求线程全量重写。"""

        temporary: Path | None = None
        try:
            if self.state_path is None:
                return
            with self._lock:
                snapshot = tuple(self._entries.values())
                snapshot_count = self._state_record_count
            temporary = self.state_path.with_suffix(f"{self.state_path.suffix}.tmp")
            with temporary.open("w", encoding="utf-8") as handle:
                for entry in snapshot:
                    json.dump(entry.to_dict(), handle, ensure_ascii=False, sort_keys=True)
                    handle.write("\n")
            with self._lock:
                if self._state_record_count == snapshot_count:
                    os.replace(temporary, self.state_path)
                    self._state_record_count = len(snapshot)
                    temporary = None
        except OSError as exc:
            log_event(
                "llm_cache_compaction_failed",
                {"error_type": type(exc).__name__},
            )
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
            self._compaction_scheduled = False

    def close(self) -> None:
        """停止后台压缩线程；缓存追加写入无需额外刷新。"""

        if self._compaction_executor is not None:
            self._compaction_executor.shutdown(wait=True, cancel_futures=False)
            self._compaction_executor = None

    def save_entries(self) -> None:
        """以原子写方式把当前 LLM 沉淀记录落盘到 JSONL。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            for entry in self._entries.values():
                record = entry.to_record()
                record.source_record_path = str(self.path)
                payload = record.to_dict()
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
        tmp_path.replace(self.path)

    def load_records_jsonl(self, path: Path) -> None:
        """加载统一题库 JSONL 中的 LLM 沉淀记录。"""
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = CanonicalQuestionRecord.from_dict(json.loads(line))
                if "ai_generated" not in record.tags and record.source_name != "AIGenerated":
                    continue
                if not record_should_be_indexable_by_reuse_policy(record):
                    continue
                entry = CachedLlmAnswer.from_record(
                    record,
                    record_cache_key=lambda source_record: cache_record_key(
                        source_record, cache_key
                    ),
                    optional_string=optional_string,
                    float_value=float_value,
                    int_value=int_value,
                )
                if cache_query_has_image_context(
                    QuestionQuery(
                        title=entry.title,
                        question_type=entry.question_type,
                        options=entry.options,
                    )
                ):
                    continue
                self._entries[entry.key] = entry

    def load_legacy_json(self, path: Path) -> bool:
        """加载旧版 `entries` JSON 缓存并返回是否读取到任何条目。"""
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        loaded = False
        entries = payload.get("entries") if isinstance(payload, dict) else []
        for item in entries or []:
            entry = CachedLlmAnswer.from_dict(
                item,
                canonical_candidate_from_payload=canonical_candidate_from_payload,
                optional_string=optional_string,
                float_value=float_value,
                int_value=int_value,
            )
            query = QuestionQuery(
                title=entry.title,
                question_type=entry.question_type,
                options=entry.options,
            )
            if cache_query_has_image_context(query):
                continue
            if not decide_answer_reuse(
                query,
                answer_text=entry.answer_text,
                candidate_answer=entry.candidate_answer,
            ).reusable:
                continue
            self._entries.setdefault(entry.key, entry)
            loaded = True
        return loaded


def cache_key(query: QuestionQuery) -> str:
    """根据标准化题型、题干和选项构建缓存键。"""
    title_key = normalize_text(query.title)
    type_key = normalize_text(query.question_type or "unknown")
    options_key = "|".join(normalize_options(query.options))
    return f"{type_key}\n{title_key}\n{options_key}"


def cache_query_has_image_context(query: QuestionQuery) -> bool:
    """图片 URL 题不进入 AI 缓存，避免历史图片答案被重复复用。"""

    return bool(normalize_image_urls(query.image_urls, (query.title,)))


# 兼容局部旧调用时保留的私有别名。
def _record_cache_key(record):
    return cache_record_key(record, cache_key)


def _is_cacheable_model_answer(query, answer, min_confidence):
    return is_cacheable_model_answer(query, answer, min_confidence, answer_shape_is_valid)


_answer_shape_is_valid = answer_shape_is_valid
_optional_string = optional_string
_canonical_candidate_from_payload = canonical_candidate_from_payload
_float_value = float_value
_int_value = int_value
