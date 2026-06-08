"""API 层请求模型定义。

本模块只负责声明 HTTP 请求体的数据契约，避免把 Pydantic 模型散落在路由文件里。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class QueryPayload(BaseModel):
    """`/query` 与 `/ocs/query` 共用的 JSON 请求体。"""

    model_config = ConfigDict(extra="ignore")

    title: str = ""
    options: str | list[str] | tuple[str, ...] = ()
    type: str | None = None
    question_type: str | None = None
    request_id: str | None = None


class RegisterPayload(BaseModel):
    """账号注册请求体。"""

    model_config = ConfigDict(extra="ignore")

    username: str = ""
    password: str = ""
    email: str | None = None


class LoginPayload(BaseModel):
    """账号登录请求体。"""

    model_config = ConfigDict(extra="ignore")

    username: str = ""
    password: str = ""
    remember: bool = False


class ResetRequestPayload(BaseModel):
    """发起密码重置请求的参数。"""

    model_config = ConfigDict(extra="ignore")

    username: str = ""


class ResetConfirmPayload(BaseModel):
    """确认密码重置时提交的参数。"""

    model_config = ConfigDict(extra="ignore")

    username: str = ""
    token: str = ""
    new_password: str = ""


class TokenCreatePayload(BaseModel):
    """个人 API 令牌创建参数。"""

    model_config = ConfigDict(extra="ignore")

    description: str = ""


class BillingPayload(BaseModel):
    """积分计费配置更新参数。"""

    model_config = ConfigDict(extra="ignore")

    local_hit: int | None = None
    web_search: int | None = None
    llm_fallback: int | None = None


class UserUpdatePayload(BaseModel):
    """管理员更新用户资料时使用的参数。"""

    model_config = ConfigDict(extra="ignore")

    role: str | None = None
    points: int | None = None
    status: str | None = None


class FeedbackPayload(BaseModel):
    """答题反馈提交参数。"""

    model_config = ConfigDict(extra="ignore")

    usage_log_id: str | None = None
    title: str = ""
    content: str = ""
    image_urls: list[str] | tuple[str, ...] = ()


class SystemConfigPayload(BaseModel):
    """系统运行配置更新参数。"""

    model_config = ConfigDict(extra="ignore")

    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_stream: str | None = None
    llm_fallback: str | None = None
    llm_explain: str | None = None
    web_search_provider: str | None = None
    search_proxy: str | None = None
    llm_proxy: str | None = None
    google_search_api_key: str | None = None
    google_search_cx: str | None = None
    baidu_search_api_key: str | None = None
    ai_cache_enabled: str | None = None
    ai_cache_min_confidence: str | None = None
    ai_cache_min_confirmations: str | None = None


class RedeemCodePayload(BaseModel):
    """创建兑换码时使用的参数。"""

    model_config = ConfigDict(extra="ignore")

    kind: str = "points"
    points: int = 0
    subscription_days: int = 0
    max_uses: int = 1
    expires_at: float = 0.0


class WalletGrantPayload(BaseModel):
    """管理员手动发放钱包权益的参数。"""

    model_config = ConfigDict(extra="ignore")

    username: str = ""
    kind: str = "points"
    points: int = 0
    subscription_days: int = 0


class WalletRedeemPayload(BaseModel):
    """用户兑换兑换码的参数。"""

    model_config = ConfigDict(extra="ignore")

    code: str = ""


class NotificationReadPayload(BaseModel):
    """消息已读状态更新参数。"""

    model_config = ConfigDict(extra="ignore")

    read: bool = True


class IntegrationCreatePayload(BaseModel):
    """创建接入点参数。"""

    model_config = ConfigDict(extra="ignore")

    name: str = ""
    platform: str = "generic"
    base_url: str = ""
    token_id: str | None = None
    status: str = "active"
    description: str = ""


class IntegrationUpdatePayload(BaseModel):
    """更新接入点参数。"""

    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    platform: str | None = None
    base_url: str | None = None
    token_id: str | None = None
    status: str | None = None
    description: str | None = None


class ImportScriptGeneratePayload(BaseModel):
    """生成导入脚本参数。"""

    model_config = ConfigDict(extra="ignore")

    name: str = ""
    integration_id: str | None = None
    token_id: str | None = None
    target: str = "ocs"
    include_test_snippet: bool = True


class QuotaPackagePayload(BaseModel):
    """额度套餐创建或更新参数。"""

    model_config = ConfigDict(extra="ignore")

    name: str = ""
    kind: str = "points"
    points: int = 0
    subscription_days: int = 0
    price: float = 0.0
    status: str = "active"
    description: str = ""
    sort_order: int = 0


class RolePermissionPayload(BaseModel):
    """角色权限矩阵更新参数。"""

    model_config = ConfigDict(extra="ignore")

    permissions: list[str] | tuple[str, ...] = ()
