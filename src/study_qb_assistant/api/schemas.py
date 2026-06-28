"""API 层请求模型定义。

本模块只负责声明 HTTP 请求体的数据契约，避免把 Pydantic 模型散落在路由文件里。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


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
    invite_code: str = ""


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
    quota_limit: int = -1
    reject_low_confidence: bool = False
    min_answer_confidence: float = 0.0


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


class UsersDeletePayload(BaseModel):
    """管理员批量删除用户的参数。"""

    model_config = ConfigDict(extra="ignore")

    usernames: list[str] | tuple[str, ...] = ()


class ProfileUpdatePayload(BaseModel):
    """当前用户更新个人资料的参数。"""

    model_config = ConfigDict(extra="ignore")

    display_name: str | None = None
    email: str | None = None


class PasswordChangePayload(BaseModel):
    """当前用户修改密码的参数。"""

    model_config = ConfigDict(extra="ignore")

    old_password: str = ""
    new_password: str = ""


class FeedbackPayload(BaseModel):
    """答题反馈提交参数。"""

    model_config = ConfigDict(extra="ignore")

    usage_log_id: str | None = None
    title: str = ""
    content: str = ""
    image_urls: list[str] | tuple[str, ...] = ()
    category: str = "answer"


class FeedbackResolvePayload(BaseModel):
    """管理员处理反馈时使用的参数。"""

    model_config = ConfigDict(extra="ignore")

    status: str = "resolved"
    admin_note: str = ""
    corrected_answer: str = ""
    reward_points: int = 0


class SystemConfigPayload(BaseModel):
    """系统运行配置更新参数。"""

    model_config = ConfigDict(extra="ignore")

    smart_proto_enabled: str | None = None
    custom_proto_header: str | None = None
    default_user_points: str | None = None
    invite_bonus_points: str | None = None
    manual_grant_default_points: str | None = None
    redeem_code_default_points: str | None = None
    answer_retry_times: str | None = None


class LlmRuntimeConfigPayload(BaseModel):
    """LLM 答题运行时配置更新参数。"""

    model_config = ConfigDict(extra="ignore")

    llm_fallback: str | None = None
    llm_explain: str | None = None
    allow_known_rules: str | None = None
    no_local_bank_mode: str | None = None
    search_first: str | None = None
    self_consistency_repeats: str | None = None
    web_search_provider: str | None = None
    web_search_configs: str | None = None
    search_proxy: str | None = None
    llm_proxy: str | None = None
    google_search_api_key: str | None = None
    google_search_cx: str | None = None
    baidu_search_api_key: str | None = None
    llm_cache_enabled: str | None = None
    llm_cache_min_confidence: str | None = None
    llm_cache_min_confirmations: str | None = None


class LlmModelCreatePayload(BaseModel):
    """新增大模型配置参数。"""

    model_config = ConfigDict(extra="ignore")

    name: str = ""
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    role: str = "backup"
    priority: int = 100
    stream: bool = True
    max_completion_tokens: int = 700
    timeout_seconds: float = 30.0
    status: str = "active"


class LlmModelUpdatePayload(BaseModel):
    """更新大模型配置参数。"""

    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    role: str | None = None
    priority: int | None = None
    stream: bool | None = None
    max_completion_tokens: int | None = None
    timeout_seconds: float | None = None
    status: str | None = None


class RedeemCodePayload(BaseModel):
    """创建兑换码时使用的参数。"""

    model_config = ConfigDict(extra="forbid")

    kind: str = "points"
    points: int = 0
    max_uses: int = 1
    expires_at: float = 0.0

    @field_validator("kind")
    @classmethod
    def points_only_kind(cls, value: str) -> str:
        """兑换码只保留积分类型，旧订阅类型请求直接拒绝。"""

        if (value or "points").strip() != "points":
            raise ValueError("兑换码类型仅支持 points")
        return "points"


class WalletGrantPayload(BaseModel):
    """管理员手动发放钱包权益的参数。"""

    model_config = ConfigDict(extra="forbid")

    username: str = ""
    kind: str = "points"
    points: int = 0

    @field_validator("kind")
    @classmethod
    def points_only_kind(cls, value: str) -> str:
        """钱包手动发放只保留积分类型。"""

        if (value or "points").strip() != "points":
            raise ValueError("钱包发放类型仅支持 points")
        return "points"


class WalletRedeemPayload(BaseModel):
    """用户兑换兑换码的参数。"""

    model_config = ConfigDict(extra="ignore")

    code: str = ""


class NotificationReadPayload(BaseModel):
    """消息已读状态更新参数。"""

    model_config = ConfigDict(extra="ignore")

    read: bool = True


class ImportScriptGeneratePayload(BaseModel):
    """生成导入脚本参数。"""

    model_config = ConfigDict(extra="ignore")

    name: str = ""
    token_id: str | None = None
    target: str = "ocs"
    include_test_snippet: bool = True


class ImportScriptCreatePayload(BaseModel):
    """创建导入脚本模板参数。"""

    model_config = ConfigDict(extra="ignore")

    name: str = ""
    target: str = "ocs"
    description: str = ""
    script_template: str = ""
    content: str = ""
    config_items: list[dict] = []
    requires_token: bool = True
    tags: list[str] | tuple[str, ...] = ()
    is_default: bool = False
    status: str = "active"


class RolePermissionPayload(BaseModel):
    """角色权限矩阵更新参数。"""

    model_config = ConfigDict(extra="ignore")

    permissions: list[str] | tuple[str, ...] = ()


class QuestionUpdatePayload(BaseModel):
    """题库记录状态与答案更新参数。"""

    model_config = ConfigDict(extra="ignore")

    title_raw: str | None = None
    question_type: str | None = None
    options_raw: list[str] | tuple[str, ...] | None = None
    answer_raw: str | None = None
    status: str | None = None
    answer: str | None = None
    answer_text: str | None = None
    explanation: str | None = None
    subject: str | None = None
    tags: list[str] | tuple[str, ...] | None = None
