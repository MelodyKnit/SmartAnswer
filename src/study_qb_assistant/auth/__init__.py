"""本地账号鉴权模块。

该包提供仅依赖 Python 标准库的用户存储、密码哈希、会话令牌与忘记密码令牌管理，
供本地 HTTP 控制台的登录/注册/会话体系使用。
"""

from __future__ import annotations

from .store import AuthError, AuthService

__all__ = ["AuthError", "AuthService"]
