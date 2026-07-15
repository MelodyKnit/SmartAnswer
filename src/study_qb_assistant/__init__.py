"""学习题库助手基础包。

此模块导出 AnswerService 和 CanonicalQuestionRecord，作为整个库的对外统一接口。
"""

from .answering import AnswerService
from study_qb_assistant.questions.models import CanonicalQuestionRecord
from .version import BUILD_INFO

__version__ = BUILD_INFO.version

# 导出对外公开的类，供外部调用
__all__ = ["AnswerService", "CanonicalQuestionRecord", "__version__"]
