"""OCS v2 图片配置从请求模型到图片水合、答题和答案复用的回归测试。"""

from __future__ import annotations

import base64
import hashlib
import io
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.adapters.ocs.request import parse_ocs_request  # noqa: E402
from study_qb_assistant.answering import AnswerService  # noqa: E402
from study_qb_assistant.api.contracts.query import QueryPayload  # noqa: E402
from study_qb_assistant.llm.cache import LlmAnswerCache  # noqa: E402
from study_qb_assistant.llm.providers.openai_compatible import (  # noqa: E402
    OpenAICompatibleProvider,
)
from study_qb_assistant.media.question_context import load_query_image_assets  # noqa: E402
from study_qb_assistant.media.question_images import hydrate_query_images_for_model  # noqa: E402
from study_qb_assistant.questions.models import (  # noqa: E402
    CanonicalQuestionRecord,
    ModelAnswer,
    QuestionQuery,
)
from study_qb_assistant.questions.parsing import QueryInputError  # noqa: E402
from study_qb_assistant.search import LocalQuestionIndex  # noqa: E402
from study_qb_assistant.storage.repositories.questions import (  # noqa: E402
    SqlAlchemyQuestionRepository,
)


def image_data_url(color: str) -> str:
    """生成无外部来源、可实际解码的最小测试图片。"""

    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), color=color).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def imported_query(**fields: object) -> QuestionQuery:
    """经过真实 API 请求模型，再进入 OCS 适配入口。"""

    return parse_ocs_request(QueryPayload(**fields).model_dump())


class ImageAnswerProvider:
    """按调用顺序作答，并记录实际传给模型的图片上下文。"""

    provider_name = "ocs-image-regression"

    def __init__(self, *, source_query: QuestionQuery | None = None) -> None:
        self.queries: list[QuestionQuery] = []
        self.source_query = source_query

    def answer(self, query: QuestionQuery) -> ModelAnswer:
        self.queries.append(query)
        label = "B" if len(self.queries) == 1 else "A"
        text = "否" if label == "B" else "是"
        return ModelAnswer(
            label,
            text,
            "根据本次上传的图片判断。",
            0.99,
            source_query=self.source_query,
        )


class OcsImageImportTests(unittest.TestCase):
    """验证新增图片占位字段与原有文本检索边界。"""

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.directory = Path(self.tempdir.name)
        self.image_a = image_data_url("red")
        self.image_b = image_data_url("blue")
        config_patch = patch(
            "study_qb_assistant.media.question_images.get_global_config",
            return_value=SimpleNamespace(
                ocs_images_dir=self.directory / "images",
                public_base_url="",
            ),
        )
        config_patch.start()
        self.addCleanup(config_patch.stop)

    def make_service(
        self,
        provider: ImageAnswerProvider,
        *,
        records: tuple[CanonicalQuestionRecord, ...] = (),
    ) -> tuple[AnswerService, SqlAlchemyQuestionRepository, LlmAnswerCache]:
        repository = SqlAlchemyQuestionRepository(self.directory / "questions.sqlite3")
        cache = LlmAnswerCache(
            self.directory / "answers.jsonl",
            min_confidence=0.95,
            min_confirmations=1,
        )
        service = AnswerService(
            LocalQuestionIndex(records),
            model_provider=provider,
            allow_model_fallback=True,
            allow_known_rules=False,
            llm_answer_cache=cache,
        )
        service.question_repository = repository
        return service, repository, cache

    def test_identical_image_bytes_remap_title_and_option_numbers(self) -> None:
        """不同 URL 的同内容图片去重时，题干和选项编号必须同步重映射。"""

        query = imported_query(
            title="比较 [图片1] 和 [图片3]。",
            options="A. [图片2]\nB. [图片3]",
            type="single",
            image_data_urls=[self.image_a, self.image_a, self.image_b],
        )

        self.assertEqual(query.title, "比较 [图片1] 和 [图片2]。")
        self.assertEqual(query.options, ("A. [图片1]", "B. [图片2]"))
        self.assertEqual(query.image_data_urls, (self.image_a, self.image_b))

    def test_remapped_images_keep_their_order_after_real_hydration(self) -> None:
        """实际解码、图床存储后，模型图片顺序仍与重映射后的编号一致。"""

        query = imported_query(
            title="[图片3] 与 [图片1] 的区别？",
            options="A. [图片2]\nB. [图片3]",
            type="single",
            image_data_urls=[self.image_a, self.image_a, self.image_b],
        )
        query = replace(query, service_base_url="https://study.example.test")
        hydrated = hydrate_query_images_for_model(query)
        assets = load_query_image_assets(query)
        expected_urls = tuple(
            "https://study.example.test/api/v1/media/ocs/images/"
            + hashlib.sha256(asset.content_bytes).hexdigest()
            + ".png"
            for asset in assets
        )

        self.assertEqual(hydrated.title, "[图片2] 与 [图片1] 的区别？")
        self.assertEqual(hydrated.options, ("A. [图片1]", "B. [图片2]"))
        self.assertEqual(hydrated.image_urls, expected_urls)
        self.assertEqual(len(hydrated.image_urls), 2)
        self.assertEqual(hydrated.image_data_urls, ())

    def test_distinct_image_only_questions_never_reuse_placeholder_answers(self) -> None:
        """相同占位题干、不同图片的两次查询均调用模型，且不沉淀占位题。"""

        provider = ImageAnswerProvider()
        service, repository, cache = self.make_service(provider)
        queries = tuple(
            imported_query(
                title="[图片1]",
                options="A. 是\nB. 否",
                type="single",
                image_data_urls=[image],
            )
            for image in (self.image_a, self.image_b)
        )

        results = tuple(service.query(query) for query in queries)

        self.assertEqual(len(provider.queries), 2)
        self.assertEqual(tuple(result.candidate_answer for result in results), ("B", "A"))
        self.assertTrue(all(result.ok for result in results))
        self.assertTrue(all(result.resolution_mode == "llm_fallback" for result in results))
        self.assertEqual(repository.list_question_records(keyword=""), [])
        self.assertIsNone(cache.get_trusted(queries[0]))
        self.assertIsNone(cache.get_trusted(queries[1]))

    def test_image_placeholders_bypass_matching_historical_text_record(self) -> None:
        """历史库中偶然存在相同占位文本时，仍必须读取本次图片。"""

        historical_record = CanonicalQuestionRecord(
            question_id="placeholder-record",
            title_raw="[图片1]",
            question_type="single",
            options_raw=("A. 是", "B. 否"),
            answer_raw="A",
            explanation="历史错误占位题。",
            subject="test",
            chapter=None,
            tags=(),
            source_name="test",
            source_url="",
            source_license="test",
            source_split="trusted",
            source_record_path="",
        )
        provider = ImageAnswerProvider()
        service, _repository, _cache = self.make_service(provider, records=(historical_record,))

        result = service.query(
            imported_query(
                title="[图片1]",
                options="A. 是\nB. 否",
                type="single",
                image_data_urls=[self.image_a],
            )
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.resolution_mode, "llm_fallback")
        self.assertEqual(result.candidate_answer, "B")
        self.assertEqual(len(provider.queries), 1)

    def test_image_in_option_is_not_reusable_despite_plain_text_title(self) -> None:
        """图片只出现在选项时，也不能仅按文本题干缓存答案。"""

        provider = ImageAnswerProvider()
        service, repository, cache = self.make_service(provider)
        query = imported_query(
            title="下列图形哪个符合条件？",
            options="A. [图片1]\nB. [图片2]",
            type="single",
            image_data_urls=[self.image_a, self.image_b],
        )

        first = service.query(query)
        second = service.query(query)

        self.assertTrue(first.ok)
        self.assertTrue(second.ok)
        self.assertEqual(len(provider.queries), 2)
        self.assertEqual(repository.list_question_records(keyword=""), [])
        self.assertIsNone(cache.get_trusted(query))

    def test_known_text_rule_cannot_override_the_vision_answer_during_repair(self) -> None:
        """后处理不得用部分题干匹配的静态规则替换图片模型的不同答案。"""

        provider = ImageAnswerProvider()
        service, repository, _cache = self.make_service(provider)
        service.allow_known_rules = True
        query = imported_query(
            title="截图判断 [图片1]。",
            options="A. 是\nB. 否",
            type="single",
            image_data_urls=[self.image_a],
        )
        # 文本规则给 A；本次图片模型给 B。前置规则和模型后处理均须保留图片结论。
        with patch(
            "study_qb_assistant.answering.quality.rules.BUILTIN_OPTION_RULES",
            ((('截图判断',), ('是',)),),
        ):
            result = service.query(query)

        self.assertTrue(result.ok)
        self.assertEqual(result.resolution_mode, "llm_fallback")
        self.assertEqual(result.candidate_answer, "B")
        self.assertEqual(result.answer_text, "否")
        self.assertEqual(len(provider.queries), 1)
        self.assertEqual(repository.list_question_records(keyword=""), [])

    def test_clean_recognized_text_snapshot_can_be_persisted_and_reused(self) -> None:
        """模型给出无图片占位符的完整文本快照时，保留原有文本沉淀能力。"""

        recognized_query = QuestionQuery(
            title="识别后的完整文本题干。",
            options=("A. 是", "B. 否"),
            question_type="single",
        )
        provider = ImageAnswerProvider(source_query=recognized_query)
        service, repository, cache = self.make_service(provider)
        imported = imported_query(
            title="[图片1]",
            options="A. 是\nB. 否",
            type="single",
            image_data_urls=[self.image_a],
        )

        result = service.query(imported)

        self.assertTrue(result.ok)
        self.assertEqual(result.debug["answer_source_title"], recognized_query.title)
        stored = repository.list_question_records(keyword="")
        self.assertEqual([record.title_raw for record in stored], [recognized_query.title])
        self.assertEqual(cache.get_trusted(recognized_query).candidate_answer, "B")

    def test_out_of_range_image_references_fail_before_answering(self) -> None:
        """缺图或越界占位符应在输入边界拒绝，避免模型用错误图片作答。"""

        for title, options, images in (
            ("[图片2]", "", [self.image_a]),
            ("图片题", "A. [图片2]\nB. 文字", [self.image_a]),
            ("[图片1]", "", []),
            ("[图片0]", "", [self.image_a]),
        ):
            with self.subTest(title=title, options=options):
                with self.assertRaises(QueryInputError):
                    imported_query(title=title, options=options, image_data_urls=images)

    def test_invalid_inline_image_cannot_leave_a_dangling_number(self) -> None:
        """内联图片格式或 Base64 损坏时，禁止过滤图片后保留原占位符。"""

        for invalid_image in (
            "not-an-image",
            "data:image/png;base64,A",
            "data:image/png;base64,",
        ):
            with self.subTest(invalid_image=invalid_image):
                with self.assertRaises(QueryInputError):
                    imported_query(
                        title="[图片1]",
                        image_data_urls=[invalid_image],
                    )

    def test_model_content_explicitly_labels_each_numbered_image(self) -> None:
        """视觉消息中的图片与文本编号显式绑定，避免依赖模型推测数组顺序。"""

        query = imported_query(
            title="比较 [图片1] 与 [图片2]。",
            image_data_urls=[self.image_a, self.image_b],
        )
        provider = object.__new__(OpenAICompatibleProvider)

        content = provider._message_content(query, "测试提示")

        self.assertEqual(
            content,
            [
                {"type": "text", "text": "测试提示"},
                {"type": "text", "text": "[图片1]"},
                {"type": "image_url", "image_url": {"url": self.image_a}},
                {"type": "text", "text": "[图片2]"},
                {"type": "image_url", "image_url": {"url": self.image_b}},
            ],
        )

    def test_numbered_image_limit_rejects_silent_model_truncation(self) -> None:
        """超过视觉消息上限时拒绝请求，而不是静默丢弃第七张图片。"""

        colors = ("red", "blue", "green", "yellow", "black", "white", "purple")
        images = [image_data_url(color) for color in colors]
        accepted = imported_query(
            title=" ".join(f"[图片{number}]" for number in range(1, 7)),
            image_data_urls=images[:6],
        )
        self.assertEqual(len(accepted.image_data_urls), 6)

        with self.assertRaises(QueryInputError):
            imported_query(title="[图片7]", image_data_urls=images)

        # 上限作用于去重后的实际图片数；七个原始 URL 可只对应两张图片。
        deduplicated = imported_query(
            title="[图片7]",
            image_data_urls=[self.image_a] * 6 + [self.image_b],
        )
        self.assertEqual(deduplicated.title, "[图片2]")
        self.assertEqual(len(deduplicated.image_data_urls), 2)

    def test_ordinary_web_link_is_allowed_but_unconverted_picture_is_rejected(self) -> None:
        """图片题允许普通网页链接；残留已识别图片链接表示转换不完整。"""

        query = imported_query(
            title="访问 https://example.test 后，比较截图 [图片1]。",
            image_data_urls=[self.image_a],
        )
        self.assertIn("https://example.test", query.title)
        for extension in ("png", "svg", "jpeg"):
            with self.subTest(extension=extension), self.assertRaises(QueryInputError):
                imported_query(
                    title=f"比较 [图片1] 和 https://cdn.example.test/missing.{extension}",
                    image_data_urls=[self.image_a],
                )


if __name__ == "__main__":
    unittest.main()
