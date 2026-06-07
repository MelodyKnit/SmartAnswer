"""数据摄入读取器的样本测试模块。

本模块包含针对 CMMLU, M3KE, AGIEval 三类主流中英文评估数据集的解析读取器测试。
测试主要验证：
1. 字段映射和元数据规范化是否正确；
2. 多选题及空答案的过滤；
3. 列表类型答案的规整化拼接（如 ["A", "B"] 拼接为 "A#B"）。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


# 将项目源文件目录 src 添加到 Python 路径中，以便能够正确导入项目模块
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.ingestion import (  # noqa: E402
    iter_agieval_records,
    iter_cmmlu_records,
    iter_m3ke_records,
)
from study_qb_assistant.ingestion.catalog import iter_source_records  # noqa: E402


class IngestionReaderTests(unittest.TestCase):
    """测试不同数据集解析读取器的单元测试类。"""

    def test_cmmlu_reader_maps_expected_fields(self) -> None:
        """测试 CMMLU 数据集读取器，验证字段和元数据是否正确映射。
        
        通过读取预置的 `anatomy.csv` 数据，检查包括题目类型、原始答案、
        学科分类、数据集版本、许可协议等字段是否符合期望。
        """
        source_path = PROJECT_ROOT / "data" / "raw" / "cmmlu-upstream" / "data" / "dev" / "anatomy.csv"

        # 迭代获取第一条记录
        record = next(iter_cmmlu_records(source_path))

        # 断言字段值是否与 CSV 中首行记录的预期解析结果一致
        self.assertEqual(record.question_type, "single")
        self.assertEqual(record.answer_raw, "B")
        self.assertEqual(record.subject, "anatomy")
        self.assertEqual(record.source_split, "dev")
        self.assertEqual(record.source_license, "CC BY-NC-SA 4.0")
        self.assertEqual(record.options_raw[1], "肺胸膜")
        self.assertIn("cmmlu", record.tags)

    def test_m3ke_reader_maps_expected_fields(self) -> None:
        """测试 M3KE 数据集读取器，验证 JSONL 格式的字段解析。
        
        通过读取高等数学（dev）样本，校验原始选项的个数、解析出来的学科名和分类标记。
        """
        source_path = (
            PROJECT_ROOT
            / "data"
            / "raw"
            / "m3ke-upstream"
            / "data"
            / "dev"
            / "Advanced Mathematics-Natural Sciences-College.jsonl"
        )

        record = next(iter_m3ke_records(source_path))

        # 断言字段规范化映射结果
        self.assertEqual(record.question_type, "single")
        self.assertEqual(record.answer_raw, "D")
        self.assertEqual(record.subject, "Advanced Mathematics")
        self.assertEqual(record.source_split, "dev")
        self.assertEqual(record.source_license, "unknown-needs-confirmation")
        self.assertEqual(len(record.options_raw), 4)
        self.assertIn("Natural Sciences", record.tags)

    def test_agieval_reader_maps_expected_fields(self) -> None:
        """测试 AGIEval 数据集读取器，验证高考物理真题的解析规范化。
        
        检查元数据字段中是否正确保留了具体的高考真题卷来源信息。
        """
        source_path = (
            PROJECT_ROOT
            / "data"
            / "raw"
            / "agieval-upstream"
            / "data"
            / "v1_1"
            / "gaokao-physics.jsonl"
        )

        record = next(iter_agieval_records(source_path))

        # 验证物理卷首题解析映射是否正常
        self.assertEqual(record.question_type, "single")
        self.assertEqual(record.answer_raw, "A")
        self.assertEqual(record.subject, "gaokao-physics")
        self.assertEqual(record.source_split, "v1_1")
        self.assertEqual(record.source_license, "follow-original-dataset-licenses")
        self.assertEqual(len(record.options_raw), 4)
        self.assertEqual(record.metadata["source"], "2017年高考真题 物理（山东卷)")

    def test_agieval_mcq_catalog_filters_records_without_answers(self) -> None:
        """测试 AGIEval 目录索引加载器，验证是否自动过滤了无答案的无效记录。"""
        records = list(iter_source_records(PROJECT_ROOT, "agieval-mcq"))

        # 确保加载出了有效的记录条数，并全部为单选题且拥有非空原始答案
        self.assertGreater(len(records), 1000)
        self.assertTrue(all(record.question_type == "single" for record in records))
        self.assertTrue(all(record.answer_raw for record in records))

    def test_agieval_reader_normalizes_list_answers(self) -> None:
        """测试 AGIEval 读取器在遇到列表格式答案时的规整化行为。
        
        对于一些多选题，数据集提供的标签是一个列表（例如 ["A", "B"]）。
        需要将其规范化为井号拼接的字符串（如 "A#B"），以便系统统一存储和对比。
        """
        # 模拟包含列表型 label 的行数据
        content = (
            '{"passage": null, "question": "demo", "options": ["A", "B"], '
            '"label": ["A", "B"], "answer": null}\n'
        )

        # 写入临时文件，执行解析测试
        with tempfile.TemporaryDirectory() as directory:
            source_dir = Path(directory) / "v1_1"
            source_dir.mkdir()
            source_path = source_dir / "demo.jsonl"
            source_path.write_text(content, encoding="utf-8")
            records = list(iter_agieval_records(source_path))

        # 验证列表型答案 ["A", "B"] 是否被规范地拼接为了 "A#B"
        self.assertEqual(records[0].answer_raw, "A#B")


if __name__ == "__main__":
    unittest.main()
