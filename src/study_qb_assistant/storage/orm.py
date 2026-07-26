"""SQLAlchemy ORM 表定义。"""

from __future__ import annotations

from sqlalchemy import Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """ORM 基类。"""


class UserEntity(Base):
    """用户表。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))
    salt: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(256))
    email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    points: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[float] = mapped_column(Float)
    invite_code: Mapped[str] = mapped_column(String(64), default="", index=True)
    invited_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    reset_token_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    reset_expires_at: Mapped[float] = mapped_column(Float, default=0.0)


class RoleEntity(Base):
    """可分配给用户的角色与权限集合。"""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(String(255), default="")
    permissions_json: Mapped[str] = mapped_column(Text, default="[]")
    is_system: Mapped[int] = mapped_column(Integer, default=0, index=True)
    created_at: Mapped[float] = mapped_column(Float, index=True)
    updated_at: Mapped[float] = mapped_column(Float, index=True)


class EmailVerificationCodeEntity(Base):
    """邮箱验证码表。"""

    __tablename__ = "email_verification_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(256), index=True)
    purpose: Mapped[str] = mapped_column(String(32), index=True)
    code_hash: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[float] = mapped_column(Float, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    send_ip_hash: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[float] = mapped_column(Float, index=True)
    consumed_at: Mapped[float] = mapped_column(Float, default=0.0, index=True)


class ApiTokenEntity(Base):
    """API 令牌表。"""

    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    key_mask: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[float] = mapped_column(Float)
    last_used_at: Mapped[float] = mapped_column(Float, default=0.0)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    quota_used: Mapped[int] = mapped_column(Integer, default=0)
    quota_limit: Mapped[int] = mapped_column(Integer, default=-1)
    reject_low_confidence: Mapped[int] = mapped_column(Integer, default=0)
    min_answer_confidence: Mapped[float] = mapped_column(Float, default=0.0)


class QuestionEntity(Base):
    """数据库题库表。"""

    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    title_raw: Mapped[str] = mapped_column(Text)
    question_type: Mapped[str] = mapped_column(String(64), index=True)
    options_raw: Mapped[str] = mapped_column(Text, default="[]")
    answer_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject: Mapped[str] = mapped_column(String(128), default="default", index=True)
    chapter: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tags: Mapped[str] = mapped_column(Text, default="[]")
    source_name: Mapped[str] = mapped_column(String(128), default="", index=True)
    source_url: Mapped[str] = mapped_column(Text, default="")
    source_license: Mapped[str] = mapped_column(String(128), default="")
    source_split: Mapped[str] = mapped_column(String(64), default="")
    source_record_path: Mapped[str] = mapped_column(Text, default="")
    passage: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str] = mapped_column("metadata", Text, default="{}")
    status: Mapped[str] = mapped_column(String(64), default="active", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[float] = mapped_column(Float, index=True)
    updated_at: Mapped[float] = mapped_column(Float, index=True)
    title_normalized: Mapped[str] = mapped_column(Text, default="")
    legacy_metadata_json: Mapped[str] = mapped_column("metadata_json", Text, default="{}")
    origin_kind: Mapped[str] = mapped_column(String(64), default="")
    record_status: Mapped[str] = mapped_column(String(64), default="active")
    provider_name: Mapped[str] = mapped_column(String(255), default="")
    confirmations: Mapped[int] = mapped_column(Integer, default=0)
    conflicts: Mapped[int] = mapped_column(Integer, default=0)
    review_required: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[int] = mapped_column(Integer, default=1)


class UsageLogEntity(Base):
    """使用日志表。"""

    __tablename__ = "usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    log_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    token_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(Text)
    question_type: Mapped[str] = mapped_column(String(64))
    resolution_mode: Mapped[str] = mapped_column(String(64))
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    points_cost: Mapped[int] = mapped_column(Integer, default=0)
    provider: Mapped[str] = mapped_column(String(128), default="")
    elapsed_ms: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[float] = mapped_column(Float, index=True)
    request_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    client_ip: Mapped[str] = mapped_column(String(64), default="")
    question_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    source_name: Mapped[str] = mapped_column(String(255), default="")
    source_type: Mapped[str] = mapped_column(String(64), default="")
    source_id: Mapped[str] = mapped_column(String(128), default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    context_json: Mapped[str] = mapped_column(Text, default="{}")


class FeedbackEntity(Base):
    """反馈表。"""

    __tablename__ = "feedbacks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feedback_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    usage_log_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    image_urls: Mapped[str] = mapped_column(Text, default="[]")
    category: Mapped[str] = mapped_column(String(64), default="answer")
    status: Mapped[str] = mapped_column(String(32), default="open")
    admin_note: Mapped[str] = mapped_column(Text, default="")
    corrected_answer: Mapped[str] = mapped_column(Text, default="")
    reward_points: Mapped[int] = mapped_column(Integer, default=0)
    handled_by: Mapped[str] = mapped_column(String(64), default="")
    handled_at: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[float] = mapped_column(Float, index=True)
    question_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    question_title: Mapped[str] = mapped_column(Text, default="")
    question_type: Mapped[str] = mapped_column(String(64), default="")
    answer_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_mode: Mapped[str] = mapped_column(String(64), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    request_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    source_name: Mapped[str] = mapped_column(String(255), default="")
    source_type: Mapped[str] = mapped_column(String(64), default="")
    source_id: Mapped[str] = mapped_column(String(128), default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    context_json: Mapped[str] = mapped_column(Text, default="{}")


class RedeemCodeEntity(Base):
    """兑换码表。"""

    __tablename__ = "redeem_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    code: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(32))
    points: Mapped[int] = mapped_column(Integer, default=0)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    used_uses: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[float] = mapped_column(Float, index=True)
    expires_at: Mapped[float] = mapped_column(Float, default=0.0)


class WalletOrderEntity(Base):
    """钱包订单表。"""

    __tablename__ = "wallet_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    points_delta: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(64), default="")
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="completed")
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[float] = mapped_column(Float, index=True)


class SettingEntity(Base):
    """平台设置键值表。"""

    __tablename__ = "settings"
    __table_args__ = (UniqueConstraint("scope", "key", name="uq_settings_scope_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(64), index=True)
    key: Mapped[str] = mapped_column(String(128))
    value: Mapped[str] = mapped_column(Text, default="")


class NotificationEntity(Base):
    """消息中心通知表。"""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    notification_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    level: Mapped[str] = mapped_column(String(32), default="info")
    category: Mapped[str] = mapped_column(String(64), default="system")
    title: Mapped[str] = mapped_column(String(255), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    read: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[float] = mapped_column(Float, index=True)


class NotificationReadReceiptEntity(Base):
    """通知中心用户已读回执表。"""

    __tablename__ = "notification_read_receipts"
    __table_args__ = (
        UniqueConstraint("user_id", "source", "item_id", name="uq_notification_receipt_user_item"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    item_id: Mapped[str] = mapped_column(String(64), index=True)
    item_updated_at: Mapped[float] = mapped_column(Float, default=0.0)
    read_at: Mapped[float] = mapped_column(Float, index=True)


class AnnouncementEntity(Base):
    """系统公告表。"""

    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    announcement_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(120), default="", index=True)
    content: Mapped[str] = mapped_column(Text, default="")
    level: Mapped[str] = mapped_column(String(32), default="info", index=True)
    audience: Mapped[str] = mapped_column(String(32), default="all", index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    pinned: Mapped[int] = mapped_column(Integer, default=0, index=True)
    starts_at: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    ends_at: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[float] = mapped_column(Float, index=True)
    updated_at: Mapped[float] = mapped_column(Float, index=True)
    published_at: Mapped[float] = mapped_column(Float, default=0.0, index=True)


class ImportScriptEntity(Base):
    """导入脚本表。"""

    __tablename__ = "import_scripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    script_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    integration_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    token_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    target: Mapped[str] = mapped_column(String(64), default="ocs")
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[float] = mapped_column(Float, index=True)
    updated_at: Mapped[float] = mapped_column(Float, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    requires_token: Mapped[int] = mapped_column(Integer, default=1)
    tags: Mapped[str] = mapped_column(Text, default="[]")
    builtin: Mapped[int] = mapped_column(Integer, default=0)
    is_default: Mapped[int] = mapped_column(Integer, default=0)
    ocs_config: Mapped[str] = mapped_column(Text, default="[]")


class LlmModelEntity(Base):
    """大模型接入配置表。"""

    __tablename__ = "llm_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    base_url: Mapped[str] = mapped_column(String(512), default="")
    model: Mapped[str] = mapped_column(String(255), default="")
    api_key: Mapped[str] = mapped_column(Text, default="")
    role: Mapped[str] = mapped_column(String(32), default="backup")
    priority: Mapped[int] = mapped_column(Integer, default=100)
    stream: Mapped[int] = mapped_column(Integer, default=1)
    max_completion_tokens: Mapped[int] = mapped_column(Integer, default=700)
    timeout_seconds: Mapped[float] = mapped_column(Float, default=30.0)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[float] = mapped_column(Float, index=True)
    updated_at: Mapped[float] = mapped_column(Float, index=True)


class LlmCallTraceEntity(Base):
    """大模型调用追溯表。"""

    __tablename__ = "llm_call_traces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    request_id: Mapped[str] = mapped_column(String(128), index=True, default="")
    phase: Mapped[str] = mapped_column(String(64), index=True, default="")
    model_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    model_name: Mapped[str] = mapped_column(String(128), index=True, default="")
    base_url: Mapped[str] = mapped_column(String(512), default="")
    provider: Mapped[str] = mapped_column(String(64), default="")
    question_title: Mapped[str] = mapped_column(Text, default="")
    prompt: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[str] = mapped_column(Text, default="[]")
    response_text: Mapped[str] = mapped_column(Text, default="")
    candidate_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    ok: Mapped[int] = mapped_column(Integer, default=1)
    error: Mapped[str] = mapped_column(Text, default="")
    elapsed_ms: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[float] = mapped_column(Float, index=True)


class ImageGenerationModelEntity(Base):
    """独立于聊天模型的生图模型配置表。"""

    __tablename__ = "image_generation_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    provider: Mapped[str] = mapped_column(String(64), default="openai-images")
    base_url: Mapped[str] = mapped_column(String(512), default="")
    model: Mapped[str] = mapped_column(String(255), default="")
    api_key: Mapped[str] = mapped_column(Text, default="")
    timeout_seconds: Mapped[float] = mapped_column(Float, default=60.0)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    capabilities: Mapped[str] = mapped_column(Text, default="text-to-image,1024x1024")
    protocol_config: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[float] = mapped_column(Float, index=True)
    updated_at: Mapped[float] = mapped_column(Float, index=True)


class ImageGenerationJobEntity(Base):
    """用户文本生图任务表。"""

    __tablename__ = "image_generation_jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_image_generation_job_idempotency"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    prompt: Mapped[str] = mapped_column(Text, default="")
    size: Mapped[str] = mapped_column(String(32), default="1024x1024")
    output_options: Mapped[str] = mapped_column(Text, default="{}")
    model_id: Mapped[str] = mapped_column(String(64), index=True)
    model_name: Mapped[str] = mapped_column(String(255), default="")
    model_snapshot: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    points_cost: Mapped[int] = mapped_column(Integer, default=0)
    reservation_order_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), default="")
    error_code: Mapped[str] = mapped_column(String(64), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[float] = mapped_column(Float, index=True)
    started_at: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    completed_at: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    updated_at: Mapped[float] = mapped_column(Float, index=True)
    expires_at: Mapped[float] = mapped_column(Float, default=0.0, index=True)


class ImageGenerationAssetEntity(Base):
    """生图任务输出资产表。"""

    __tablename__ = "image_generation_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    mime_type: Mapped[str] = mapped_column(String(64), default="image/png")
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    byte_size: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[float] = mapped_column(Float, index=True)
    deleted_at: Mapped[float] = mapped_column(Float, default=0.0, index=True)


class ImageGenerationTraceEntity(Base):
    """生图供应商调用追溯表。"""

    __tablename__ = "image_generation_traces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    model_id: Mapped[str] = mapped_column(String(64), index=True)
    model_name: Mapped[str] = mapped_column(String(255), default="")
    provider: Mapped[str] = mapped_column(String(64), default="")
    phase: Mapped[str] = mapped_column(String(64), default="generate", index=True)
    provider_request_id: Mapped[str] = mapped_column(String(255), default="")
    ok: Mapped[int] = mapped_column(Integer, default=1)
    elapsed_ms: Mapped[float] = mapped_column(Float, default=0.0)
    error_code: Mapped[str] = mapped_column(String(64), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[float] = mapped_column(Float, index=True)
