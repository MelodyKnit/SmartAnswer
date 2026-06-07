"""特定题库数据导入入口模块。

该包包含了从各种公开数据集（如 AGIEval、CMMLU、M3KE）解析和导入题目数据的具体实现。
"""

from .agieval import iter_agieval_records
from .cmmlu import iter_cmmlu_records
from .m3ke import iter_m3ke_records

__all__ = [
    "iter_agieval_records",
    "iter_cmmlu_records",
    "iter_m3ke_records",
]
