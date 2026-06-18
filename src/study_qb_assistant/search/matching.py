"""本地题库高稳匹配策略。

该模块把题库匹配拆成“规范键精确命中、n-gram 召回、RapidFuzz 精排”三步，
避免旧实现对所有记录做全量编辑距离扫描。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import difflib
import re
import string
import unicodedata

from ..models import CanonicalQuestionRecord, QuestionQuery
from ..normalization import normalize_options
from .support import is_ai_record, record_options_match

try:  # RapidFuzz 是项目依赖；保留降级让开发环境未更新时仍可运行测试。
    from rapidfuzz import fuzz  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - 仅用于未安装依赖的本地兜底。
    fuzz = None


CHOICE_TYPES = {"single", "multiple"}
FUZZY_CANDIDATE_LIMIT = 80
STRONG_TITLE_THRESHOLD = 0.92
WEAK_TITLE_THRESHOLD = 0.86
MIN_TOP_GAP = 0.04
HIGH_OPTION_THRESHOLD = 0.92
PUNCTUATION_TO_DROP = (
    string.punctuation
    + "，。！？、：；“”‘’（）()【】[]《》〈〉「」『』〔〕…·￥"
)

QUESTION_PREFIX_RE = re.compile(
    r"^(?:第?\d+题[.。、:]*)?"
    r"(?:(?:单选题|多选题|判断题|填空题|简答题|问答题|选择题)"
    r"(?:[（(]\s*\d+(?:\.\d+)?\s*分\s*[）)])?"
    r"|[（(]\s*\d+(?:\.\d+)?\s*分\s*[）)])",
    re.IGNORECASE,
)
LEADING_NUMBER_RE = re.compile(r"^\d+[.。、:：]\s*")
BLANK_PLACEHOLDER_RE = re.compile(
    r"(?:[【\[]\s*\d+\s*[】\]])?\s*[_＿—－-]{2,}|[【\[]\s*\d+\s*[】\]]"
)
WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class QuestionMatchKey:
    """题库精确匹配使用的稳定键。"""

    question_type: str
    title_key: str
    option_signature: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MatchCandidate:
    """检索候选及其诊断评分。"""

    record: CanonicalQuestionRecord
    confidence: float
    match_stage: str
    title_score: float
    option_score: float
    candidate_count: int
    top_gap: float


class QuestionMatcher:
    """面向内存题库的两阶段检索器。"""

    def __init__(self, records: tuple[CanonicalQuestionRecord, ...]) -> None:
        """构建精确键、题干键和 n-gram 倒排索引。"""

        self.records = records
        self.exact_key_index: dict[QuestionMatchKey, list[int]] = {}
        self.title_key_index: dict[str, list[int]] = {}
        self.ngram_inverted_index: dict[str, set[int]] = {}
        for index, record in enumerate(records):
            title_key = normalize_match_title(record.title_raw)
            option_signature = normalize_options(record.options_raw)
            key = QuestionMatchKey(
                question_type=normalize_question_type(record.question_type),
                title_key=title_key,
                option_signature=option_signature,
            )
            self.exact_key_index.setdefault(key, []).append(index)
            self.title_key_index.setdefault(title_key, []).append(index)
            for gram in title_ngrams(title_key):
                self.ngram_inverted_index.setdefault(gram, set()).add(index)

    def status(self) -> dict[str, int]:
        """返回索引结构统计，便于运行时诊断。"""

        return {
            "exact_key_count": len(self.exact_key_index),
            "title_key_count": len(self.title_key_index),
            "ngram_key_count": len(self.ngram_inverted_index),
        }

    def exact_match(self, query: QuestionQuery) -> MatchCandidate | None:
        """执行严格且高可信的规范键匹配。"""

        query_title_key = normalize_match_title(query.title)
        query_options = normalize_options(query.options)
        key = QuestionMatchKey(
            question_type=normalize_question_type(query.question_type),
            title_key=query_title_key,
            option_signature=query_options,
        )
        exact_indexes = self.exact_key_index.get(key) or []
        exact_candidates = self.valid_candidates(exact_indexes, query)
        if exact_candidates:
            record = self.rank_by_option_and_review(exact_candidates, query)[0]
            return MatchCandidate(record, 0.99, "exact_key", 1.0, 1.0, len(exact_candidates), 1.0)

        title_indexes = self.title_key_index.get(query_title_key) or []
        title_candidates = self.valid_candidates(title_indexes, query)
        trusted_title_candidates = [
            record for record in title_candidates if self.title_key_candidate_is_safe(record, query)
        ]
        if not trusted_title_candidates:
            return None
        record = self.rank_by_option_and_review(trusted_title_candidates, query)[0]
        option_score = option_similarity(record.options_raw, query.options)
        return MatchCandidate(
            record=record,
            confidence=0.99,
            match_stage="title_key",
            title_score=1.0,
            option_score=option_score,
            candidate_count=len(trusted_title_candidates),
            top_gap=1.0,
        )

    def fuzzy_match(self, query: QuestionQuery) -> MatchCandidate | None:
        """先通过 n-gram 倒排召回候选，再进行高置信精排。"""

        query_title_key = normalize_match_title(query.title)
        candidate_indexes = self.recall_candidate_indexes(query_title_key)
        scored: list[MatchCandidate] = []
        for index in candidate_indexes:
            record = self.records[index]
            if is_ai_record(record):
                continue
            title_score = title_similarity(normalize_match_title(record.title_raw), query_title_key)
            option_score = option_similarity(record.options_raw, query.options)
            if not self.fuzzy_candidate_is_safe(record, query, title_score, option_score):
                continue
            confidence = combined_confidence(record, query, title_score, option_score)
            scored.append(
                MatchCandidate(
                    record=record,
                    confidence=confidence,
                    match_stage="ngram_fuzzy",
                    title_score=title_score,
                    option_score=option_score,
                    candidate_count=len(candidate_indexes),
                    top_gap=0.0,
                )
            )
        if not scored:
            return None
        scored.sort(
            key=lambda item: (
                item.confidence,
                title_similarity(normalize_match_title(item.record.title_raw), query_title_key),
                review_priority(item.record),
            ),
            reverse=True,
        )
        best = scored[0]
        second_score = scored[1].confidence if len(scored) > 1 else 0.0
        top_gap = best.confidence - second_score
        if len(scored) > 1 and top_gap < MIN_TOP_GAP:
            return None
        return MatchCandidate(
            record=best.record,
            confidence=round(best.confidence, 4),
            match_stage=best.match_stage,
            title_score=round(best.title_score, 4),
            option_score=round(best.option_score, 4),
            candidate_count=best.candidate_count,
            top_gap=round(top_gap, 4),
        )

    def recall_candidate_indexes(self, title_key: str) -> list[int]:
        """用 n-gram 重合度召回候选，替代全量扫描。"""

        grams = title_ngrams(title_key)
        if not grams:
            return []
        hits: Counter[int] = Counter()
        for gram in grams:
            for index in self.ngram_inverted_index.get(gram, ()):
                hits[index] += 1
        return [
            index
            for index, _ in hits.most_common(FUZZY_CANDIDATE_LIMIT)
        ]

    def valid_candidates(
        self, indexes: list[int], query: QuestionQuery
    ) -> list[CanonicalQuestionRecord]:
        """过滤 AI 缓存题的严格选项约束。"""

        records: list[CanonicalQuestionRecord] = []
        for index in indexes:
            record = self.records[index]
            if is_ai_record(record) and not record_options_match(record, query):
                continue
            records.append(record)
        return records

    def title_key_candidate_is_safe(
        self, record: CanonicalQuestionRecord, query: QuestionQuery
    ) -> bool:
        """判断同规范题干候选是否能安全复用。"""

        if is_ai_record(record):
            return record_options_match(record, query)
        if is_choice_query(record, query) and record.options_raw and query.options:
            return ordered_option_similarity(record.options_raw, query.options) >= HIGH_OPTION_THRESHOLD
        return True

    def fuzzy_candidate_is_safe(
        self,
        record: CanonicalQuestionRecord,
        query: QuestionQuery,
        title_score: float,
        option_score: float,
    ) -> bool:
        """控制模糊命中的安全阈值，防止近似题错配。"""

        if not record.options_raw and not query.options:
            return False
        if title_score >= STRONG_TITLE_THRESHOLD:
            if is_choice_query(record, query) and record.options_raw and query.options:
                return ordered_option_similarity(record.options_raw, query.options) >= HIGH_OPTION_THRESHOLD
            return True
        if title_score < WEAK_TITLE_THRESHOLD:
            return False
        if is_choice_query(record, query):
            return bool(
                record.options_raw
                and query.options
                and ordered_option_similarity(record.options_raw, query.options)
                >= HIGH_OPTION_THRESHOLD
            )
        return normalize_question_type(query.question_type) in {"completion", "judgement", "judge"}

    def rank_by_option_and_review(
        self, records: list[CanonicalQuestionRecord], query: QuestionQuery
    ) -> list[CanonicalQuestionRecord]:
        """同题候选优先使用已审核记录，其次使用选项匹配更高的记录。"""

        return sorted(
            records,
            key=lambda record: (review_priority(record), option_similarity(record.options_raw, query.options)),
            reverse=True,
        )


def normalize_question_type(value: str | None) -> str:
    """标准化题型字符串。"""

    return (value or "unknown").strip().casefold()


def normalize_match_title(value: str | None) -> str:
    """生成题库匹配专用题干键。"""

    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", value)
    text = WHITESPACE_RE.sub("", text)
    text = QUESTION_PREFIX_RE.sub("", text)
    text = LEADING_NUMBER_RE.sub("", text)
    text = BLANK_PLACEHOLDER_RE.sub("{blank}", text)
    text = text.translate(str.maketrans("", "", PUNCTUATION_TO_DROP))
    return text.casefold()


def title_ngrams(value: str) -> set[str]:
    """为中文短题干生成 2-gram 与 3-gram 混合特征。"""

    if not value:
        return set()
    if len(value) <= 3:
        return {value}
    grams: set[str] = set()
    for size in (2, 3):
        if len(value) < size:
            continue
        grams.update(value[index : index + size] for index in range(len(value) - size + 1))
    return grams


def title_similarity(left: str, right: str) -> float:
    """计算题干相似度，优先使用 RapidFuzz。"""

    if not left or not right:
        return 0.0
    if fuzz is None:
        return difflib.SequenceMatcher(None, left, right).ratio()
    ratio = fuzz.ratio(left, right) / 100.0
    weighted = fuzz.WRatio(left, right) / 100.0
    return max(ratio, weighted)


def option_similarity(record_options: tuple[str, ...], query_options: tuple[str, ...]) -> float:
    """计算选项集合与顺序综合相似度。"""

    record_normalized = normalize_options(record_options)
    query_normalized = normalize_options(query_options)
    if not record_normalized or not query_normalized:
        return 0.0
    if record_normalized == query_normalized:
        return 1.0
    record_set = set(record_normalized)
    query_set = set(query_normalized)
    overlap = record_set & query_set
    set_score = len(overlap) / max(len(record_set), len(query_set))
    order_score = ordered_option_similarity(record_options, query_options)
    return (set_score * 0.75) + (order_score * 0.25)


def ordered_option_similarity(
    record_options: tuple[str, ...], query_options: tuple[str, ...]
) -> float:
    """计算选项按页面顺序逐项一致的比例。"""

    record_normalized = normalize_options(record_options)
    query_normalized = normalize_options(query_options)
    if not record_normalized or not query_normalized:
        return 0.0
    total = max(len(record_normalized), len(query_normalized))
    same_position = sum(
        1
        for left, right in zip(record_normalized, query_normalized, strict=False)
        if left == right
    )
    return same_position / total


def combined_confidence(
    record: CanonicalQuestionRecord,
    query: QuestionQuery,
    title_score: float,
    option_score: float,
) -> float:
    """综合题干与选项得分。"""

    if record.options_raw and query.options:
        return (title_score * 0.82) + (option_score * 0.18)
    return title_score


def is_choice_query(record: CanonicalQuestionRecord, query: QuestionQuery) -> bool:
    """判断当前匹配是否属于答案标签依赖选项顺序的题型。"""

    record_type = normalize_question_type(record.question_type)
    query_type = normalize_question_type(query.question_type)
    return record_type in CHOICE_TYPES or query_type in CHOICE_TYPES


def review_priority(record: CanonicalQuestionRecord) -> int:
    """用户确认/批改过的同题记录优先级高于基础导入题库。"""

    markers = {
        "chaoxing_reviewed",
        "reviewed",
        "user-local-reviewed",
        "user_reviewed",
    }
    raw_values = {
        record.source_license,
        record.source_split,
        record.source_name,
        *record.tags,
        *record.metadata.values(),
    }
    normalized = {str(item).lower() for item in raw_values if item}
    return 1 if normalized & markers else 0
