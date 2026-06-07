"""AI 生成答案的自动沉淀题库。

该模块保留“多次一致确认后才复用”的状态机，但持久化格式使用
CanonicalQuestionRecord JSONL。也就是说，AI 答过并通过校验的题会成为
带有 ai_generated/auto_learned 标签的标准题库记录，而不是另一套专用 JSON 缓存。
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock

from .models import CanonicalQuestionRecord, ModelAnswer, QuestionQuery
from .normalization import normalize_options, normalize_text
from .option_labels import canonicalize_label_answer

# 选项的字母标签定义（支持最多6个选项）
_LABELS = ("A", "B", "C", "D", "E", "F")


@dataclass(slots=True)
class CachedAIAnswer:
    """存储单个标准化问题形式的 AI 答案元数据。

    Attributes:
        key: 缓存键，由标准化后的题型、题干和选项组合而成。
        title: 问题的题干。
        question_type: 问题类型（如单选、多选等）。
        options: 选项列表。
        candidate_answer: 候选答案（如 "A" 或 "A#B"）。
        answer_text: 答案的文本内容（可选）。
        explanation: 答案的解析/说明（可选）。
        confidence: AI 生成答案的置信度。
        confirmations: 相同答案被确认的次数。
        conflicts: 不同答案冲突的次数。
        status: 缓存项的状态（如 "pending", "trusted", "conflict"）。
        provider_name: 提交该答案的提供者/模型名称。
        created_at: 缓存项创建的时间戳。
        updated_at: 缓存项最后更新的时间戳。
    """

    key: str
    title: str
    question_type: str
    options: tuple[str, ...]
    candidate_answer: str
    answer_text: str | None
    explanation: str | None
    confidence: float
    confirmations: int
    conflicts: int
    status: str
    provider_name: str
    created_at: float
    updated_at: float

    @classmethod
    def from_dict(cls, payload: dict) -> "CachedAIAnswer":
        """从字典数据中还原缓存的答案对象。

        Args:
            payload: 包含缓存字段的字典。

        Returns:
            CachedAIAnswer: 还原后的缓存答案实例。
        """
        # 从 payload 提取字段并转换为正确类型，对空值进行降级或兜底处理
        return cls(
            key=str(payload["key"]),
            title=str(payload.get("title") or ""),
            question_type=str(payload.get("question_type") or "unknown"),
            options=tuple(str(option) for option in payload.get("options") or ()),
            candidate_answer=_canonical_candidate_from_payload(payload),
            answer_text=_optional_string(payload.get("answer_text")),
            explanation=_optional_string(payload.get("explanation")),
            confidence=float(payload.get("confidence") or 0.0),
            confirmations=int(payload.get("confirmations") or 0),
            conflicts=int(payload.get("conflicts") or 0),
            status=str(payload.get("status") or "pending"),
            provider_name=str(payload.get("provider_name") or "unknown"),
            created_at=float(payload.get("created_at") or time.time()),
            updated_at=float(payload.get("updated_at") or time.time()),
        )

    def to_dict(self) -> dict:
        """将缓存的答案对象序列化为稳定的 JSON 字典格式。

        Returns:
            dict: 序列化后的字典。
        """
        payload = asdict(self)
        # 转换 options 元组为列表以确保兼容 JSON 序列化
        payload["options"] = list(self.options)
        return payload

    @classmethod
    def from_record(cls, record: CanonicalQuestionRecord) -> "CachedAIAnswer":
        """从标准题库记录还原 AI 沉淀状态。"""
        metadata = record.metadata
        query = QuestionQuery(
            title=record.title_raw,
            question_type=record.question_type,
            options=record.options_raw,
        )
        return cls(
            key=metadata.get("ai_cache_key") or _record_cache_key(record),
            title=record.title_raw,
            question_type=record.question_type,
            options=record.options_raw,
            candidate_answer=canonicalize_label_answer(query, record.answer_raw or "") or (record.answer_raw or ""),
            answer_text=_optional_string(metadata.get("ai_answer_text")),
            explanation=record.explanation,
            confidence=_float_value(metadata.get("ai_confidence"), default=0.0),
            confirmations=_int_value(metadata.get("ai_confirmations"), default=0),
            conflicts=_int_value(metadata.get("ai_conflicts"), default=0),
            status=metadata.get("ai_status") or record.source_split or "pending",
            provider_name=metadata.get("ai_provider_name") or "unknown",
            created_at=_float_value(metadata.get("ai_created_at"), default=time.time()),
            updated_at=_float_value(metadata.get("ai_updated_at"), default=time.time()),
        )

    def to_record(self) -> CanonicalQuestionRecord:
        """把 AI 沉淀答案写成统一题库记录。"""
        record_id = f"ai:{hashlib.sha256(self.key.encode('utf-8')).hexdigest()[:24]}"
        metadata = {
            "record_origin": "ai_generated",
            "ai_cache_key": self.key,
            "ai_status": self.status,
            "ai_confirmations": str(self.confirmations),
            "ai_conflicts": str(self.conflicts),
            "ai_confidence": str(self.confidence),
            "ai_provider_name": self.provider_name,
            "ai_created_at": str(self.created_at),
            "ai_updated_at": str(self.updated_at),
        }
        if self.answer_text:
            metadata["ai_answer_text"] = self.answer_text
        return CanonicalQuestionRecord(
            question_id=record_id,
            title_raw=self.title,
            question_type=self.question_type,
            options_raw=self.options,
            answer_raw=self.candidate_answer,
            explanation=self.explanation,
            subject="ai-generated",
            chapter=None,
            tags=(
                "ai_generated",
                "auto_learned",
                f"status:{self.status}",
                f"provider:{self.provider_name}",
            ),
            source_name="AIGenerated",
            source_url="",
            source_license="user-local-ai-generated",
            source_split=self.status,
            source_record_path="data/normalized/ai-learned.jsonl",
            metadata=metadata,
        )


class AIAnswerCache:
    """AI 自动沉淀题库管理类，仅在多次高置信度一致时才信任答案。

    类名保留旧的 Cache 命名以兼容已有调用；持久化格式已统一为标准题库 JSONL。
    """

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
            min_confidence: 允许沉淀的最低置信度阈值，默认为 0.95。
            min_confirmations: 晋升为受信任（trusted）状态所需的最低一致确认次数，默认为 2。
        """
        self.path = Path(path)
        # 限制置信度阈值在 0.0 ~ 1.0 之间
        self.min_confidence = min(max(min_confidence, 0.0), 1.0)
        # 确认次数最少为 1 次
        self.min_confirmations = max(1, min_confirmations)
        self.legacy_paths = tuple(Path(value) for value in legacy_paths)
        self._lock = Lock()
        self._entries: dict[str, CachedAIAnswer] = {}
        # 初始化时从本地加载已有的缓存数据
        self._load()

    def get_trusted(self, query: QuestionQuery) -> CachedAIAnswer | None:
        """获取匹配该查询且状态为受信任的缓存答案。

        Args:
            query: 问题查询对象。

        Returns:
            CachedAIAnswer | None: 受信任的缓存答案，若不存在或不匹配则返回 None。
        """
        key = cache_key(query)
        with self._lock:
            entry = self._entries.get(key)
            # 仅返回存在且状态为 "trusted" 的项
            if entry is None or entry.status != "trusted":
                return None
            # 校验候选答案格式是否与当前的查询选项相符，防止选项发生变化导致缓存失效
            if not _answer_shape_is_valid(query, entry.candidate_answer):
                return None
            return entry

    def record_model_answer(
        self,
        query: QuestionQuery,
        answer: ModelAnswer,
        *,
        provider_name: str,
    ) -> CachedAIAnswer | None:
        """记录新的模型答案，并在满足一致性条件时提升其状态。

        Args:
            query: 问题查询对象。
            answer: 模型生成的答案对象。
            provider_name: 提供该答案的提供者/模型名称。

        Returns:
            CachedAIAnswer | None: 更新后的缓存答案项；若答案不满足缓存条件则返回 None。
        """
        # 检查是否满足基本的缓存标准（如置信度与答案格式）
        if not _is_cacheable_model_answer(query, answer, self.min_confidence):
            return None

        now = time.time()
        key = cache_key(query)
        candidate = canonicalize_label_answer(query, str(answer.candidate_answer or "").strip()) or str(answer.candidate_answer).strip()
        with self._lock:
            existing = self._entries.get(key)
            # 如果是该问题首次被记录，则创建一个待确认的缓存条目
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
                    # 如果 min_confirmations 设置为 1，直接晋升为 trusted
                    status="trusted" if self.min_confirmations <= 1 else "pending",
                    provider_name=provider_name,
                    created_at=now,
                    updated_at=now,
                )
                self._entries[key] = entry
                self._save()
                return entry

            # 如果新结果与已有答案冲突，标记为 conflict 并递增冲突数
            existing_candidate = canonicalize_label_answer(query, existing.candidate_answer) or existing.candidate_answer
            if normalize_text(existing_candidate) != normalize_text(candidate):
                existing.conflicts += 1
                existing.status = "conflict"
                existing.updated_at = now
                self._save()
                return existing

            # 若答案一致，增加确认计数并合并非空字段
            existing.confirmations += 1
            existing.answer_text = answer.answer_text or existing.answer_text
            existing.explanation = answer.explanation or existing.explanation
            existing.confidence = max(existing.confidence, min(max(answer.confidence, 0.0), 1.0))
            existing.provider_name = provider_name
            existing.updated_at = now
            # 若无冲突且一致确认次数达到预设阈值，则晋升为 trusted
            if existing.conflicts == 0 and existing.confirmations >= self.min_confirmations:
                existing.status = "trusted"
            self._save()
            return existing

    def status(self) -> dict:
        """获取非敏感的缓存统计信息和配置状态。

        Returns:
            dict: 包含缓存是否启用、路径、条目数量、各状态分布和配置参数的字典。
        """
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

    def _load(self) -> None:
        """从磁盘加载 AI 沉淀题库，并兼容旧版 JSON 缓存。"""
        loaded_legacy = False
        if self.path.exists():
            if self.path.suffix.lower() == ".jsonl":
                self._load_records_jsonl(self.path)
            else:
                self._load_legacy_json(self.path)
        for legacy_path in self.legacy_paths:
            if legacy_path.exists() and legacy_path.resolve() != self.path.resolve():
                loaded_legacy = self._load_legacy_json(legacy_path) or loaded_legacy
        if loaded_legacy and self.path.suffix.lower() == ".jsonl":
            self._save()

    def _save(self) -> None:
        """以原子操作将当前 AI 沉淀记录写入标准题库 JSONL。

        首先写入临时文件，然后通过重命名替换原文件，以防止写入中断导致数据损坏。
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            for entry in self._entries.values():
                record = entry.to_record()
                record.source_record_path = str(self.path)
                payload = record.to_dict()
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
        # 原子替换现有文件
        tmp_path.replace(self.path)

    def _load_records_jsonl(self, path: Path) -> None:
        """加载标准题库 JSONL 中的 AI 沉淀记录。"""
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = CanonicalQuestionRecord.from_dict(json.loads(line))
                if "ai_generated" not in record.tags and record.source_name != "AIGenerated":
                    continue
                entry = CachedAIAnswer.from_record(record)
                self._entries[entry.key] = entry

    def _load_legacy_json(self, path: Path) -> bool:
        """加载旧版 entries JSON 缓存。返回是否成功读到任何条目。"""
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        loaded = False
        entries = payload.get("entries") if isinstance(payload, dict) else []
        for item in entries or []:
            entry = CachedAIAnswer.from_dict(item)
            self._entries.setdefault(entry.key, entry)
            loaded = True
        return loaded


def cache_key(query: QuestionQuery) -> str:
    """根据标准化的题干、题型和选项集合构建唯一的缓存键。

    Args:
        query: 问题查询对象。

    Returns:
        str: 由换行符分隔的缓存键字符串。
    """
    title_key = normalize_text(query.title)
    type_key = normalize_text(query.question_type or "unknown")
    # 选项经过标准化并用管道符连接
    options_key = "|".join(normalize_options(query.options))
    return f"{type_key}\n{title_key}\n{options_key}"


def _record_cache_key(record: CanonicalQuestionRecord) -> str:
    query = QuestionQuery(
        title=record.title_raw,
        options=record.options_raw,
        question_type=record.question_type,
    )
    return cache_key(query)


def _is_cacheable_model_answer(
    query: QuestionQuery,
    answer: ModelAnswer,
    min_confidence: float,
) -> bool:
    """判断模型生成的答案是否满足缓存的基本条件。

    条件包括置信度达到阈值、候选答案不为空，且候选答案的格式与问题选项数匹配。

    Args:
        query: 问题查询对象。
        answer: 模型生成的答案对象。
        min_confidence: 最低置信度要求。

    Returns:
        bool: 是否可缓存。
    """
    if answer.confidence < min_confidence:
        return False
    if not answer.candidate_answer:
        return False
    return _answer_shape_is_valid(query, answer.candidate_answer)


def _answer_shape_is_valid(query: QuestionQuery, candidate_answer: str) -> bool:
    """检查候选答案的格式/形状是否与问题相符。

    如果问题有选项，则候选答案（按 '#' 分割）中的每个部分都必须是合法的选项字母（如 A-F 范围内）。

    Args:
        query: 问题查询对象。
        candidate_answer: 候选答案字符串（如 "A" 或 "A#B"）。

    Returns:
        bool: 候选答案格式是否有效。
    """
    candidate = candidate_answer.strip()
    if not candidate:
        return False
    if not query.options:
        return True
    return canonicalize_label_answer(query, candidate) is not None


def _optional_string(value: object) -> str | None:
    """处理可选的字符串值，将空字符串或 None 统一转换为 None。

    Args:
        value: 待处理的对象。

    Returns:
        str | None: 清理后的字符串或 None。
    """
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _canonical_candidate_from_payload(payload: dict) -> str:
    query = QuestionQuery(
        title=str(payload.get("title") or ""),
        question_type=str(payload.get("question_type") or "unknown"),
        options=tuple(str(option) for option in payload.get("options") or ()),
    )
    candidate = str(payload.get("candidate_answer") or "")
    return canonicalize_label_answer(query, candidate) or candidate


def _float_value(value: object, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_value(value: object, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
