"""AI 自动沉淀题库服务。

该模块保留“多次一致确认后才复用”的状态机，但把记录模型和辅助判断拆到独立文件中，
主文件只负责缓存状态机、持久化协调和对外接口。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from threading import Lock

from .records import CachedAIAnswer
from .support import (
    answer_shape_is_valid,
    cache_record_key,
    canonical_candidate_from_payload,
    float_value,
    int_value,
    is_cacheable_model_answer,
    optional_string,
)
from ..models import CanonicalQuestionRecord, ModelAnswer, QuestionQuery
from ..normalization import normalize_options, normalize_text
from ..option_labels import canonicalize_label_answer


class AIAnswerCache:
    """AI 自动沉淀题库管理器。"""

    def __init__(
        self,
        path: str | Path,
        *,
        min_confidence: float = 0.95,
        min_confirmations: int = 2,
        legacy_paths: tuple[str | Path, ...] = (),
    ) -> None:
        """初始化 AI 自动沉淀题库管理器。

        Args:
            path: AI 自动沉淀题库 JSONL 存储路径。
            min_confidence: 允许沉淀的最低置信度阈值。
            min_confirmations: 晋升为 `trusted` 所需的一致确认次数。
            legacy_paths: 旧版 JSON 缓存路径集合，用于迁移。
        """
        self.path = Path(path)
        self.min_confidence = min(max(min_confidence, 0.0), 1.0)
        self.min_confirmations = max(1, min_confirmations)
        self.legacy_paths = tuple(Path(value) for value in legacy_paths)
        self._lock = Lock()
        self._entries: dict[str, CachedAIAnswer] = {}
        self.load_entries()

    def get_trusted(self, query: QuestionQuery) -> CachedAIAnswer | None:
        """获取匹配该查询且状态为受信任的缓存答案。"""
        key = cache_key(query)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry.status != "trusted":
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
    ) -> CachedAIAnswer | None:
        """记录新的模型答案，并在满足条件时提升其状态。"""
        if not is_cacheable_model_answer(query, answer, self.min_confidence, answer_shape_is_valid):
            return None

        now = time.time()
        key = cache_key(query)
        candidate = canonicalize_label_answer(query, str(answer.candidate_answer or "").strip()) or str(answer.candidate_answer).strip()
        with self._lock:
            existing = self._entries.get(key)
            if existing is None:
                entry = CachedAIAnswer(
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
                    status="trusted" if self.min_confirmations <= 1 else "pending",
                    provider_name=provider_name,
                    created_at=now,
                    updated_at=now,
                )
                self._entries[key] = entry
                self.save_entries()
                return entry

            existing_candidate = canonicalize_label_answer(query, existing.candidate_answer) or existing.candidate_answer
            if normalize_text(existing_candidate) != normalize_text(candidate):
                existing.conflicts += 1
                existing.status = "conflict"
                existing.updated_at = now
                self.save_entries()
                return existing

            existing.confirmations += 1
            existing.answer_text = answer.answer_text or existing.answer_text
            existing.explanation = answer.explanation or existing.explanation
            existing.confidence = max(existing.confidence, min(max(answer.confidence, 0.0), 1.0))
            existing.provider_name = provider_name
            existing.updated_at = now
            if existing.conflicts == 0 and existing.confirmations >= self.min_confirmations:
                existing.status = "trusted"
            self.save_entries()
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
        """从磁盘加载 AI 沉淀记录，并兼容旧版 JSON 缓存迁移。"""
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

    def save_entries(self) -> None:
        """以原子写方式把当前 AI 沉淀记录落盘到 JSONL。"""
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
        """加载统一题库 JSONL 中的 AI 沉淀记录。"""
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = CanonicalQuestionRecord.from_dict(json.loads(line))
                if "ai_generated" not in record.tags and record.source_name != "AIGenerated":
                    continue
                entry = CachedAIAnswer.from_record(
                    record,
                    record_cache_key=lambda source_record: cache_record_key(source_record, cache_key),
                    optional_string=optional_string,
                    float_value=float_value,
                    int_value=int_value,
                )
                self._entries[entry.key] = entry

    def load_legacy_json(self, path: Path) -> bool:
        """加载旧版 `entries` JSON 缓存并返回是否读取到任何条目。"""
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        loaded = False
        entries = payload.get("entries") if isinstance(payload, dict) else []
        for item in entries or []:
            entry = CachedAIAnswer.from_dict(
                item,
                canonical_candidate_from_payload=canonical_candidate_from_payload,
                optional_string=optional_string,
                float_value=float_value,
                int_value=int_value,
            )
            self._entries.setdefault(entry.key, entry)
            loaded = True
        return loaded


def cache_key(query: QuestionQuery) -> str:
    """根据标准化题型、题干和选项构建缓存键。"""
    title_key = normalize_text(query.title)
    type_key = normalize_text(query.question_type or "unknown")
    options_key = "|".join(normalize_options(query.options))
    return f"{type_key}\n{title_key}\n{options_key}"


# 兼容局部旧调用时保留的私有别名。
_record_cache_key = lambda record: cache_record_key(record, cache_key)
_is_cacheable_model_answer = lambda query, answer, min_confidence: is_cacheable_model_answer(
    query, answer, min_confidence, answer_shape_is_valid
)
_answer_shape_is_valid = answer_shape_is_valid
_optional_string = optional_string
_canonical_candidate_from_payload = canonical_candidate_from_payload
_float_value = float_value
_int_value = int_value
