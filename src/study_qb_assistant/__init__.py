"""学习题库助手基础包。

此模块导出 AnswerService 和 CanonicalQuestionRecord，作为整个库的对外统一接口。
"""

from .answering import AnswerService
from .models import CanonicalQuestionRecord

__version__ = "0.1.19"

# 导出对外公开的类，供外部调用
__all__ = ["AnswerService", "CanonicalQuestionRecord", "__version__"]
