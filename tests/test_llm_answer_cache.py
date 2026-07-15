"""LLM 自动沉淀题库持久化与旧缓存迁移测试。"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.llm.cache import LlmAnswerCache, cache_key  # noqa: E402
from study_qb_assistant.questions.models import QuestionQuery  # noqa: E402


class LlmAnswerCachePersistenceTests(unittest.TestCase):
    """验证 LLM 答案使用统一题库 JSONL 持久化。"""

    def test_legacy_json_cache_is_migrated_to_ai_learned_jsonl(self) -> None:
        """旧版 entries JSON 缓存应迁移为带 LLM 沉淀标记的标准题库记录。"""
        query = QuestionQuery(
            title="单选题(1分)旧缓存迁移题",
            options=("正确项", "干扰项"),
            question_type="single",
        )
        now = time.time()

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            legacy_path = base / "runtime" / "ai-answer-cache.json"
            learned_path = base / "normalized" / "ai-learned.jsonl"
            legacy_path.parent.mkdir(parents=True)
            legacy_payload = {
                "version": 1,
                "entries": [
                    {
                        "key": cache_key(query),
                        "title": query.title,
                        "question_type": query.question_type,
                        "options": list(query.options),
                        "candidate_answer": "A",
                        "answer_text": "正确项",
                        "explanation": "旧缓存中的解析。",
                        "confidence": 0.99,
                        "confirmations": 2,
                        "conflicts": 0,
                        "status": "trusted",
                        "provider_name": "legacy-provider",
                        "created_at": now,
                        "updated_at": now,
                    }
                ],
            }
            legacy_path.write_text(json.dumps(legacy_payload, ensure_ascii=False), encoding="utf-8")

            cache = LlmAnswerCache(learned_path, legacy_paths=(legacy_path,))
            trusted = cache.get_trusted(query)
            records = _read_jsonl(learned_path)

        self.assertIsNotNone(trusted)
        self.assertEqual(trusted.candidate_answer, "A")
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["source_name"], "AIGenerated")
        self.assertEqual(record["source_record_path"], str(learned_path))
        self.assertIn("ai_generated", record["tags"])
        self.assertEqual(record["metadata"]["ai_status"], "trusted")
        self.assertEqual(record["metadata"]["ai_provider_name"], "legacy-provider")

    def test_legacy_multiple_choice_labels_are_canonicalized_on_load(self) -> None:
        """旧版多选缓存载入时应规整为按选项顺序输出。"""
        query = QuestionQuery(
            title="多选题(1分)旧缓存顺序迁移题",
            options=("甲", "乙", "丙", "丁"),
            question_type="multiple",
        )
        now = time.time()

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            legacy_path = base / "runtime" / "ai-answer-cache.json"
            learned_path = base / "normalized" / "ai-learned.jsonl"
            legacy_path.parent.mkdir(parents=True)
            legacy_payload = {
                "version": 1,
                "entries": [
                    {
                        "key": cache_key(query),
                        "title": query.title,
                        "question_type": query.question_type,
                        "options": list(query.options),
                        "candidate_answer": "C#A#B",
                        "answer_text": "甲；乙；丙",
                        "explanation": "旧缓存中的解析。",
                        "confidence": 0.99,
                        "confirmations": 2,
                        "conflicts": 0,
                        "status": "trusted",
                        "provider_name": "legacy-provider",
                        "created_at": now,
                        "updated_at": now,
                    }
                ],
            }
            legacy_path.write_text(json.dumps(legacy_payload, ensure_ascii=False), encoding="utf-8")

            cache = LlmAnswerCache(learned_path, legacy_paths=(legacy_path,))
            trusted = cache.get_trusted(query)
            records = _read_jsonl(learned_path)

        self.assertIsNotNone(trusted)
        self.assertEqual(trusted.candidate_answer, "A#B#C")
        self.assertEqual(records[0]["answer_raw"], "A#B#C")

    def test_legacy_open_text_cache_is_not_loaded_as_trusted_answer(self) -> None:
        """历史开放性长文本缓存不应再作为可信 AI 答案复用。"""
        query = QuestionQuery(
            title="操作系统学习总结及心得体会，不少于2000字",
            question_type="completion",
        )
        long_answer = "学习心得：" + "课程学习让我理解了进程、内存、文件系统和设备管理。" * 12
        now = time.time()

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            legacy_path = base / "runtime" / "ai-answer-cache.json"
            learned_path = base / "normalized" / "ai-learned.jsonl"
            legacy_path.parent.mkdir(parents=True)
            legacy_payload = {
                "version": 1,
                "entries": [
                    {
                        "key": cache_key(query),
                        "title": query.title,
                        "question_type": query.question_type,
                        "options": [],
                        "candidate_answer": long_answer,
                        "answer_text": long_answer,
                        "explanation": "历史缓存中的开放题答案。",
                        "confidence": 0.99,
                        "confirmations": 2,
                        "conflicts": 0,
                        "status": "trusted",
                        "provider_name": "legacy-provider",
                        "created_at": now,
                        "updated_at": now,
                    }
                ],
            }
            legacy_path.write_text(json.dumps(legacy_payload, ensure_ascii=False), encoding="utf-8")

            cache = LlmAnswerCache(learned_path, legacy_paths=(legacy_path,))
            trusted = cache.get_trusted(query)
            records = _read_jsonl(learned_path) if learned_path.exists() else []

        self.assertIsNone(trusted)
        self.assertEqual(records, [])


def _read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


if __name__ == "__main__":
    unittest.main()
