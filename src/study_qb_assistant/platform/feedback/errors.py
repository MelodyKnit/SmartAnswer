"""反馈领域可预期业务错误定义。"""

from __future__ import annotations


class FeedbackOperationError(RuntimeError):
    """可安全转换为 API 业务错误的反馈操作异常。"""

    def __init__(self, code: str, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
