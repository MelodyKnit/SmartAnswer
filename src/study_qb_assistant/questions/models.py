"""数据导入与本地检索层共享的题库数据模型定义。

此模块包含数据导入、检索决议以及模型提供商之间交互所用的标准数据模型类（Dataclasses）。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CanonicalQuestionRecord:
    """在数据导入和本地检索代码中通用的标准化题库题目记录。

    Attributes:
        question_id: 题目的唯一标识符。
        title_raw: 题目的原始题干文本。
        question_type: 题目的标准化类型（如 "single", "multiple" 等）。
        options_raw: 原始选项文本列表（元组）。
        answer_raw: 标准化后的答案标签或文本（例如 "A" 或 "A#B" 或 填空文本）。
        explanation: 题目的答案解析或说明。
        subject: 题目所属科目。
        chapter: 题目所属章节。
        tags: 题目分类标签（元组）。
        source_name: 数据源名称。
        source_url: 数据源链接。
        source_license: 数据源使用的授权许可。
        source_split: 数据集的切分属性（如 "train", "test"）。
        source_record_path: 本地源文件中的相对记录路径。
        passage: 与题目关联的文章或背景阅读材料。
        metadata: 其他与题目关联的自定义键值对元数据字典。
    """

    question_id: str
    title_raw: str
    question_type: str
    options_raw: tuple[str, ...]
    answer_raw: str | None
    explanation: str | None
    subject: str
    chapter: str | None
    tags: tuple[str, ...]
    source_name: str
    source_url: str
    source_license: str
    source_split: str
    source_record_path: str
    passage: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def as_choice_map(self) -> dict[str, str]:
        """将 options_raw 按顺序映射为 A/B/C/D/E/F 字母选项映射表。

        Returns:
            dict[str, str]: 键为字母标签、值为对应选项原始文本的字典。
        """
        labels = ("A", "B", "C", "D", "E", "F")
        return {label: value for label, value in zip(labels, self.options_raw, strict=False)}

    def to_dict(self) -> dict:
        """将当前题目记录序列化为一个稳定的可兼容 JSON 的字典格式。

        Returns:
            dict: 包含题目所有字段的字典，且 tuple 被转换为 list。
        """
        status = self.metadata.get("status") or self.metadata.get("ai_status") or self.source_split
        confidence = self.metadata.get("confidence") or self.metadata.get("ai_confidence") or "0"
        created_at = self.metadata.get("created_at") or self.metadata.get("ai_created_at") or "0"
        updated_at = self.metadata.get("updated_at") or self.metadata.get("ai_updated_at") or "0"
        return {
            "question_id": self.question_id,
            "title_raw": self.title_raw,
            "question_type": self.question_type,
            "options_raw": list(self.options_raw),
            "answer_raw": self.answer_raw,
            "explanation": self.explanation,
            "subject": self.subject,
            "chapter": self.chapter,
            "tags": list(self.tags),
            "source_name": self.source_name,
            "source_url": self.source_url,
            "source_license": self.source_license,
            "source_split": self.source_split,
            "source_record_path": self.source_record_path,
            "passage": self.passage,
            "metadata": self.metadata,
            "status": status or "active",
            "confidence": _float_metadata(confidence),
            "created_at": _float_metadata(created_at),
            "updated_at": _float_metadata(updated_at),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "CanonicalQuestionRecord":
        """从 `to_dict` 序列化的字典中还原题目记录实例。

        Args:
            payload: 反序列化出的字典数据。

        Returns:
            CanonicalQuestionRecord: 还原出的记录实例。
        """
        return cls(
            question_id=payload["question_id"],
            title_raw=payload["title_raw"],
            question_type=payload["question_type"],
            options_raw=tuple(payload.get("options_raw") or ()),
            answer_raw=payload.get("answer_raw"),
            explanation=payload.get("explanation"),
            subject=payload["subject"],
            chapter=payload.get("chapter"),
            tags=tuple(payload.get("tags") or ()),
            source_name=payload["source_name"],
            source_url=payload["source_url"],
            source_license=payload["source_license"],
            source_split=payload["source_split"],
            source_record_path=payload["source_record_path"],
            passage=payload.get("passage"),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(slots=True)
class QuestionQuery:
    """本地检索服务接收的标准化题目查询结构体。

    Attributes:
        title: 待查询的题目题干。
        options: 待查询题目的选项列表（元组），默认为空。
        question_type: 题目类型（例如 "single", "multiple" 等），默认为 "unknown"。
        request_id: 请求流水号或标识符，便于追踪，默认为 None。
        page_url: 当前题目所在页面地址，可用于浏览器上下文补抓图片。
        image_capture_status: 浏览器侧图片抓取结果摘要，例如 `inline_complete` 或 `url_only_fallback`。
        image_capture_failures: 浏览器侧未能转成内联图片的数量。
        image_urls: 题干图片链接列表，仅作为答题上下文，不作为可复用题干本体。
        image_data_urls: 题干图片的内联 data URL 列表，仅用于本次识图，不写入题库。
        option_image_urls: 选项标签到图片链接的映射，仅作为答题上下文。
        option_image_data_urls: 选项标签到图片 data URL 的映射，仅用于本次识图。
        service_base_url: 当前服务对外基础地址，用于生成模型可访问的本地图床 URL。
    """

    title: str
    options: tuple[str, ...] = ()
    question_type: str = "unknown"
    request_id: str | None = None
    page_url: str | None = None
    image_capture_status: str = ""
    image_capture_failures: int = 0
    image_urls: tuple[str, ...] = ()
    image_data_urls: tuple[str, ...] = ()
    option_image_urls: dict[str, str] = field(default_factory=dict)
    option_image_data_urls: dict[str, str] = field(default_factory=dict)
    service_base_url: str | None = None


@dataclass(slots=True)
class QueryResult:
    """由检索决议服务返回的带有数据来源标记的答案候选及分析结果。

    Attributes:
        ok: 决议是否成功（例如，题目是否存在，模型 fallback 是否正常响应等）。
        query: 发起查询的原始 QuestionQuery 对象。
        candidate_answer: 决议得出的标准化答案（如 "A" 或 "A#B" 或 填空文本）。
        answer_text: 对应标准化答案的实际文字选项内容。
        explanation: 答案解析或解题说明。
        confidence: 对该决议结果的置信度。
        resolution_mode: 解析模式标识（如 "exact_match", "fuzzy_match", "llm_fallback", "known_rule" 等）。
        review_required: 是否需要人工审核。
        sources: 提供该结果的数据源或模型来源详情元组。
        error_code: 决议失败时的错误码。
        error_message: 决议失败时的详细错误描述信息。
        debug: 调试诊断键值对字典。
    """

    ok: bool
    query: QuestionQuery
    candidate_answer: str | None
    answer_text: str | None
    explanation: str | None
    confidence: float
    resolution_mode: str
    review_required: bool
    sources: tuple[dict, ...] = ()
    error_code: str | None = None
    error_message: str | None = None
    debug: dict[str, str] = field(default_factory=dict)

    def to_api_dict(self) -> dict:
        """根据标准 API 响应协议，将当前 QueryResult 序列化为字典。

        Returns:
            dict: 符合 API 协议定义的响应字典。
        """
        if not self.ok:
            # 决议失败时返回带有错误说明的结构
            return {
                "ok": False,
                "request_id": self.query.request_id,
                "query": {
                    "title": self.query.title,
                    "type": self.query.question_type,
                    "options": list(self.query.options),
                    "image_urls": list(self.query.image_urls),
                    "option_image_urls": dict(self.query.option_image_urls),
                },
                "error": {
                    "code": self.error_code or "QUERY_FAILED",
                    "message": self.error_message or "query failed",
                },
                "debug": dict(self.debug),
            }

        # 决议成功时返回包含查询本身、答案结果、数据源列表及调试信息的完整结构
        return {
            "ok": True,
            "request_id": self.query.request_id,
            "query": {
                "title": self.query.title,
                "type": self.query.question_type,
                "options": list(self.query.options),
                "image_urls": list(self.query.image_urls),
                "option_image_urls": dict(self.query.option_image_urls),
            },
            "result": {
                "candidate_answer": self.candidate_answer,
                "answer_text": self.answer_text,
                "explanation": self.explanation,
                "confidence": self.confidence,
                "resolution_mode": self.resolution_mode,
                "review_required": self.review_required,
            },
            "sources": list(self.sources),
            "debug": {
                "retrieval_strategy": "exact_then_fuzzy",
                "provider": self.debug.get("provider", "local-normalized-jsonl"),
                **self.debug,
            },
        }


@dataclass(slots=True)
class ModelAnswer:
    """由大模型提供商模块返回的结构化原始解答对象。

    Attributes:
        candidate_answer: 模型提取出的标准化选项标签组合（如 "A" 或 "A#B"）或填空文本。
        answer_text: 选项文本内容。
        explanation: 模型生成的解题思路或说明。
        confidence: 模型给出该答案的置信度评分（0.0 ~ 1.0）。
        question_form: 模型识别出的题目形态，用于辅助后续复用策略判断。
        reuse_policy: 模型建议的答案复用策略，不直接绕过服务端护栏。
        reuse_reason: 模型给出复用策略的简短原因。
        reuse_confidence: 模型对复用策略判断的置信度评分（0.0 ~ 1.0）。
        source_query: 模型实际依据的题目文本，通常用于 OCR 成功后的题库沉淀。
    """

    candidate_answer: str | None
    answer_text: str | None
    explanation: str | None
    confidence: float
    question_form: str | None = None
    reuse_policy: str | None = None
    reuse_reason: str | None = None
    reuse_confidence: float | None = None
    source_query: QuestionQuery | None = None


def _float_metadata(value: object) -> float:
    """安全解析题库 metadata 中的浮点字段。"""

    try:
        return float(str(value or "0"))
    except (TypeError, ValueError):
        return 0.0
