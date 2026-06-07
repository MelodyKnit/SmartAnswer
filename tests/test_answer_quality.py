"""模型答案修复规则与质量评估的单元测试模块。

本模块包含针对回答质量模块中各种自动修复规则（包括已知问题的硬编码规则、
填空题杂音过滤、判断题冲突解析等）以及缓存安全性判定逻辑的测试用例。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# 将项目源文件目录 src 添加到 Python 路径中，以便能够正确导入项目模块
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from study_qb_assistant.answer_quality import is_cache_safe_answer, repair_model_answer  # noqa: E402
import study_qb_assistant.answer_quality as answer_quality_module  # noqa: E402
from study_qb_assistant.models import ModelAnswer, QuestionQuery  # noqa: E402

_TEST_RULES_PAYLOAD = {
    "option_rules": [
        {"needles": ["国家安全工作", "以()为基础"], "answers": ["经济安全"]},
        {"needles": ["2018年12月", "八字方针"], "answers": ["巩固", "增强", "提升", "畅通"]},
        {"needles": ["建设美丽中国", "为主的方针"], "answers": ["保护优先", "节约优先", "自然恢复"]},
        {"needles": ["从现在到2020年", "决胜期"], "answers": ["建成小康社会"]},
        {"needles": ["复兴之路", "中华民族的昨天"], "answers": ["“雄关漫道真如铁”"]},
        {"needles": ["全面深化改革", "总目标"], "answers": ["完善和发展中国特色社会主义制度、推进国家治理体系和治理能力现代化"]},
        {"needles": ["四个伟大", "属于"], "answers": ["进行伟大斗争", "建设伟大工程", "推进伟大事业", "实现伟大梦想"]},
        {"needles": ["2020年7月30日", "高质量发展", "目标定位"], "answers": ["更高质量", "更有效率", "更加公平", "更可持续", "更为安全"]},
        {"needles": ["社会主要矛盾", "已经转化为"], "answers": ["人民日益增长的美好生活需要", "不平衡不充分的发展"]},
        {"needles": ["两个维护", "核心地位", "党中央权威"], "answers": ["对"]},
        {"needles": ["社会主要矛盾", "总依据", "发生了变化"], "answers": ["错"]},
        {"needles": ["2013年11月", "湖南", "精准扶贫"], "answers": ["对"]},
    ],
    "completion_rules": [
        {"needles": ["现代战争", "核心战斗力"], "answer": "科技"},
    ],
}


class AnswerQualityTests(unittest.TestCase):
    """测试模型答案修复及质量控制逻辑的测试类。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tempdir = tempfile.TemporaryDirectory()
        cls._rules_path = Path(cls._tempdir.name) / "answer-quality-rules.json"
        cls._rules_path.write_text(json.dumps(_TEST_RULES_PAYLOAD, ensure_ascii=False), encoding="utf-8")
        cls._previous_rules_path = os.environ.get("STQB_ANSWER_RULES_PATH")
        os.environ["STQB_ANSWER_RULES_PATH"] = str(cls._rules_path)
        _clear_rule_caches()

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._previous_rules_path is None:
            os.environ.pop("STQB_ANSWER_RULES_PATH", None)
        else:
            os.environ["STQB_ANSWER_RULES_PATH"] = cls._previous_rules_path
        _clear_rule_caches()
        cls._tempdir.cleanup()

    def test_known_formula_repairs_national_security_basis_answer(self) -> None:
        """测试对于国家安全基础相关问题的硬编码公式修复逻辑。
        
        验证当模型给出错误或低置信度的回答时，修复程序是否能通过硬编码的
        真题库公式将其修正为正确的选项（C/经济安全），并提升置信度。
        """
        # 构建国家安全基础的单选题查询
        query = QuestionQuery(
            title="单选题(1分)国家安全工作应当坚持总体国家安全观，以()为基础。",
            options=("人民安全", "政治安全", "经济安全", "军事安全"),
            question_type="single",
        )
        # 模拟模型给出了低置信度且有幻觉的回答
        hallucinated = ModelAnswer(
            candidate_answer="B",
            answer_text="政治安全",
            explanation="若严格依据标准表述，应选C。",
            confidence=0.32,
        )

        # 运行修复函数
        repaired = repair_model_answer(query, hallucinated)

        # 断言修复后的结果是否正确：应指向“经济安全”选项（即C），且置信度被提升
        self.assertEqual(repaired.candidate_answer, "C")
        self.assertEqual(repaired.answer_text, "经济安全")
        self.assertIn("经济安全", repaired.explanation or "")
        self.assertNotIn("政治安全", repaired.explanation or "")
        self.assertGreaterEqual(repaired.confidence, 0.96)

    def test_completion_question_ignores_noisy_editor_options(self) -> None:
        """测试填空题在包含编辑器杂音时是否能正确忽略并匹配出正确答案。
        
        验证当填空题选项中混入UEditor配置等网页抓取噪音时，修复逻辑能否
        识别并过滤，最终给出预期的默认正确填空答案。
        """
        # 填空题中包含网页编辑器残留脚本的选项
        query = QuestionQuery(
            title="填空题(1分)【1】____是现代战争的核心战斗力。",
            options=("window.UEDITOR_CONFIG.initialFrameWidth = 730;", "var allowPaste = \"0\";"),
            question_type="填空题",
        )

        # 对空回答运行修复逻辑
        repaired = repair_model_answer(query, ModelAnswer(None, None, None, 0.0))

        # 验证是否正确被修复为预期的“科技”
        self.assertEqual(repaired.candidate_answer, "科技")
        self.assertEqual(repaired.answer_text, "科技")

    def test_known_formula_repairs_2018_economic_work_eight_words(self) -> None:
        """测试 2018 年中央经济工作会议“八字方针”多选题的修复逻辑。
        
        验证模型因“漏选”而给出的部分正确答案是否能被自动补全为完整答案（A#B#C#D）。
        """
        # 构建“八字方针”多选题查询
        query = QuestionQuery(
            title="多选题(1分)2018年12月，中央经济工作会议提出()八字方针，为当前和今后一个时期深化供给侧结构性改革、推动经济高质量发展指明了航向。",
            options=("巩固", "增强", "提升", "畅通"),
            question_type="multiple",
        )

        # 模型原本漏选了 C (提升)，并有对应的解析提示
        repaired = repair_model_answer(query, ModelAnswer("A#B#D", None, "漏选C。", 0.6))

        # 验证是否成功补全了 C (选项变为 A#B#C#D) 并包含“畅通”
        self.assertEqual(repaired.candidate_answer, "A#B#C#D")
        self.assertIn("畅通", repaired.answer_text or "")

    def test_explanation_labels_are_reordered_into_page_order(self) -> None:
        """测试多选解释中的乱序标签会被重排成页面选项顺序。"""
        query = QuestionQuery(
            title="多选题(1分)顺序修复测试",
            options=("甲", "乙", "丙", "丁"),
            question_type="multiple",
        )

        repaired = repair_model_answer(
            query,
            ModelAnswer("D#B#A", None, "应选 D、B、A。", 0.88),
        )

        self.assertEqual(repaired.candidate_answer, "A#B#D")

    def test_known_formula_repairs_beautiful_china_policy(self) -> None:
        """测试建设美丽中国方针多选题的硬编码公式修复。
        
        验证在没有任何模型回答的情况下，是否能根据预设公式修复出正确答案（保护优先、节约优先、自然恢复为主，即 B#C#D）。
        """
        # 建设美丽中国方针多选题
        query = QuestionQuery(
            title="多选题(1分)建设美丽中国，应坚持( )为主的方针。",
            options=("效益优先", "保护优先", "节约优先", "自然恢复"),
            question_type="multiple",
        )

        repaired = repair_model_answer(query, ModelAnswer(None, None, None, 0.0))

        # 预期正确选项为 B#C#D（排除效益优先）
        self.assertEqual(repaired.candidate_answer, "B#C#D")

    def test_known_formula_repairs_xiaokang_decisive_period(self) -> None:
        """测试全面建成小康社会决胜期单选题的修复。
        
        验证空答案在经修复后是否能得到“建成小康社会”（即 B）的正确选项。
        """
        # 十九大关于全面建成小康社会决胜期的单选题
        query = QuestionQuery(
            title="单选题(1分)党的十九大指出，从现在到2020年，是全面( )决胜期。",
            options=("深化改革", "建成小康社会", "从严治党", "依法治国"),
            question_type="single",
        )

        repaired = repair_model_answer(query, ModelAnswer(None, None, None, 0.0))

        # 验证选项与文本是否正确修复
        self.assertEqual(repaired.candidate_answer, "B")
        self.assertEqual(repaired.answer_text, "建成小康社会")

    def test_known_formula_repairs_rejuvenation_road_yesterday(self) -> None:
        """测试《复兴之路》中关于中华民族“昨天”描述的单选题修复。
        
        验证修复逻辑能正确输出毛泽东诗词“雄关漫道真如铁”（即 A）。
        """
        # 复兴之路展览相关单选题
        query = QuestionQuery(
            title="单选题(1分)习近平在参观《复兴之路》展览时指出，中华民族的昨天，可以说是( )。",
            options=("“雄关漫道真如铁”", "“人间正道是沧桑”", "“长风破浪会有时”", "“柳暗花明又一村”"),
            question_type="single",
        )

        repaired = repair_model_answer(query, ModelAnswer(None, None, None, 0.0))

        # 验证结果为 A
        self.assertEqual(repaired.candidate_answer, "A")
        self.assertEqual(repaired.answer_text, "“雄关漫道真如铁”")

    def test_known_formula_repairs_deepening_reform_goal(self) -> None:
        """测试全面深化改革总目标单选题的修复。
        
        验证空答案能够成功被修复为选项 B（完善和发展中国特色社会主义制度、推进国家治理体系和治理能力现代化）。
        """
        # 全面深化改革总目标的单选题
        query = QuestionQuery(
            title="单选题(1分)习近平总书记指出，全面深化改革总目标是( )。",
            options=(
                "全面建立社会主义市场经济体制",
                "完善和发展中国特色社会主义制度、推进国家治理体系和治理能力现代化",
                "实现中国梦",
                "实现社会主义现代化",
            ),
            question_type="single",
        )

        repaired = repair_model_answer(query, ModelAnswer(None, None, None, 0.0))

        # 验证修复答案为 B
        self.assertEqual(repaired.candidate_answer, "B")

    def test_known_formula_repairs_four_greats_multiple_choice(self) -> None:
        """测试“四个伟大”多选题的修复。
        
        验证空答案能够被正确修复为全选（A#B#C#D）。
        """
        # 统揽“四个伟大”多选题
        query = QuestionQuery(
            title="多选题(1分)习近平总书记在党的十九大报告中强调，实现中华民族伟大复兴的中国梦，必须统揽“四个伟大”。以下属于“四个伟大”的是()。",
            options=("进行伟大斗争", "建设伟大工程", "推进伟大事业", "实现伟大梦想"),
            question_type="multiple",
        )

        repaired = repair_model_answer(query, ModelAnswer(None, None, None, 0.0))

        # 验证四个选项全选
        self.assertEqual(repaired.candidate_answer, "A#B#C#D")

    def test_known_formula_repairs_high_quality_development_targets(self) -> None:
        """测试高质量发展阶段定位多选题的修复。
        
        验证空答案能够正确修复为包含所有五个定位选项（A#B#C#D#E）。
        """
        # 高质量发展定位多选题
        query = QuestionQuery(
            title="多选题(1分)2020年7月30日召开的中央政治局会议，对于高质量发展阶段的目标定位是()。",
            options=("更高质量", "更有效率", "更加公平", "更可持续", "更为安全"),
            question_type="multiple",
        )

        repaired = repair_model_answer(query, ModelAnswer(None, None, None, 0.0))

        # 验证全选
        self.assertEqual(repaired.candidate_answer, "A#B#C#D#E")

    def test_known_formula_repairs_main_contradiction_multiple_choice(self) -> None:
        """测试我国社会主要矛盾多选题的修复。
        
        验证空答案能否被正确修复为选项 A#B（人民日益增长的美好生活需要 和 不平衡不充分的发展 之间的矛盾）。
        """
        # 主要矛盾多选题
        query = QuestionQuery(
            title="多选题(1分)党的十九大指出，我国社会主要矛盾已经转化为()和()之间的矛盾。",
            options=(
                "人民日益增长的美好生活需要",
                "不平衡不充分的发展",
                "人民日益增长的物质文化生活的需要",
                "落后的社会生产力",
            ),
            question_type="multiple",
        )

        repaired = repair_model_answer(query, ModelAnswer(None, None, None, 0.0))

        # 验证选项为 A#B
        self.assertEqual(repaired.candidate_answer, "A#B")

    def test_model_explanation_enumerating_correct_options_does_not_collapse_to_last_label(self) -> None:
        """测试当模型的解释中列举了所有正确选项时，答案判定不会塌陷为仅最后一个标签。
        
        有些脆弱的解析逻辑可能会错误提取解释中的最后一个字母作为最终选项。本测试验证
        修复逻辑在面对“A正确，B正确...因此四项均正确”的正常解释时，不会将原有的
        "A#B#C#D" 错误地篡改或塌陷。
        """
        query = QuestionQuery(
            title="多选题(1分)下列关于2020年全面建成小康社会，表述正确的有( )。",
            options=(
                "实现了第一个百年奋斗目标",
                "实现了中华民族千百年来的夙愿",
                "是迈向中华民族伟大复兴的关键一步",
                "是对人类社会的伟大贡献",
            ),
            question_type="multiple",
        )
        model_answer = ModelAnswer(
            "A#B#C#D",
            "全部正确",
            "A正确，B正确，C正确，D正确，因此四项均正确。",
            0.94,
        )

        repaired = repair_model_answer(query, model_answer)

        # 确保候选答案依然是全选，并没有塌陷为 D
        self.assertEqual(repaired.candidate_answer, "A#B#C#D")

    def test_conflicting_candidate_and_answer_text_is_not_cache_safe(self) -> None:
        """测试当候选答案字母与回答文本冲突时，该答案是否正确地被判定为非缓存安全。
        
        如果 candidate_answer="A" (代表对)，而 answer_text="错"，则它们相冲突，
        这类有瑕疵的回答不能被存入缓存供后续使用。
        """
        query = QuestionQuery(
            title="判断题(1分)缓存安全测试。",
            options=("对", "错"),
            question_type="judgement",
        )
        # 选项 A 对应“对”，但 answer_text 是“错”，构成冲突
        answer = ModelAnswer("A", "错", "字段冲突。", 0.99)

        # 断言其非缓存安全
        self.assertFalse(is_cache_safe_answer(query, answer))

    def test_judgement_repair_trusts_candidate_label_before_generic_error_words(self) -> None:
        """测试判断题修复逻辑在遇到解释中包含“错误”等词时的处理。
        
        当判断题答案为“对”(A)，但解释中说“错误选项是 B”时，修复程序不应误认为
        答案是“错”，而应信任候选标签 A。
        """
        query = QuestionQuery(
            title="判断题(1分)判断解析测试。",
            options=("对", "错"),
            question_type="judgement",
        )
        # 解释包含“错误”字样，但候选标签和答案文本都是“对”
        answer = ModelAnswer("A", "对", "题干正确；错误选项是B。", 0.96)

        repaired = repair_model_answer(query, answer)

        # 应保持 A/对，不应被解释中的“错误”带偏
        self.assertEqual(repaired.candidate_answer, "A")
        self.assertEqual(repaired.answer_text, "对")

    def test_known_formula_repairs_two_maintains_judgement(self) -> None:
        """测试“两个维护”判断题的修复逻辑。
        
        验证当模型将该题误判为“错”(B) 时，修复逻辑是否能依据预设公式纠正为“对”(A)。
        """
        query = QuestionQuery(
            title="判断题(1分)“两个维护”是指维护习近平总书记党中央的核心、全党的核心地位，维护党中央权威 and 集中统一领导。",
            options=("对", "错"),
            question_type="judgement",
        )

        repaired = repair_model_answer(query, ModelAnswer("B", "错", "误判。", 0.4))

        # 验证被成功修正为 A/对
        self.assertEqual(repaired.candidate_answer, "A")
        self.assertEqual(repaired.answer_text, "对")

    def test_known_formula_repairs_changed_basis_judgement_as_false(self) -> None:
        """测试关于我国社会主义建设总依据发生变化的判断题修复逻辑。
        
        虽然主要矛盾变了，但总依据没变，该说法为“错”。验证若模型误判为“对”(A) 时，
        修复逻辑能否纠正为“错”(B)。
        """
        query = QuestionQuery(
            title="判断题(1分)随着我国社会主要矛盾的变化，建设中国特色社会主义的总依据也发生了变化。",
            options=("对", "错"),
            question_type="judgement",
        )

        repaired = repair_model_answer(query, ModelAnswer("A", "对", "误判。", 0.5))

        # 验证被修正为 B/错
        self.assertEqual(repaired.candidate_answer, "B")
        self.assertEqual(repaired.answer_text, "错")

    def test_judgement_prefers_explicit_label_over_conflicting_words(self) -> None:
        """测试当判断题回答字段冲突时，修复逻辑能否根据解释倾向偏好显式纠正。
        
        如果模型输出 candidate_answer="B"(错), answer_text="错"，但解释中指出
        “正确应选A”，且置信度较低，验证修复程序能否纠正为 A/对 并提升置信度。
        """
        query = QuestionQuery(
            title="判断题(1分)模型字段冲突测试。",
            options=("对", "错"),
            question_type="judgement",
        )
        # 初始是不一致且低置信度的回答，解释明示了“正确应选A”
        inconsistent = ModelAnswer(
            candidate_answer="B",
            answer_text="错",
            explanation="题干说法是正确的。不过模型字段冲突，正确应选A。",
            confidence=0.22,
        )

        repaired = repair_model_answer(query, inconsistent)

        # 验证是否成功纠正为 A/对，并提升了置信度
        self.assertEqual(repaired.candidate_answer, "A")
        self.assertEqual(repaired.answer_text, "对")
        self.assertGreaterEqual(repaired.confidence, 0.9)

    def test_known_formula_repairs_precise_poverty_judgement_as_true(self) -> None:
        """测试精准扶贫理念首次提出时间地点判断题的修复逻辑。
        
        验证当模型误判为“错”(B) 时，修复逻辑是否能依据预设公式纠正为“对”(A)。
        """
        query = QuestionQuery(
            title="判断题(1分)2013年11月，习近平在湖南考察时，首次创造性地提出精准扶贫的重要理念。",
            options=("对", "错"),
            question_type="judgement",
        )

        repaired = repair_model_answer(query, ModelAnswer("B", "错", "误判。", 0.22))

        # 验证被修正为 A/对
        self.assertEqual(repaired.candidate_answer, "A")
        self.assertEqual(repaired.answer_text, "对")


if __name__ == "__main__":
    unittest.main()


def _clear_rule_caches() -> None:
    answer_quality_module._configured_option_rules.cache_clear()
    answer_quality_module._configured_completion_rules.cache_clear()
    answer_quality_module._load_rules_payload.cache_clear()
