"""系统配置接口请求模型。"""

from pydantic import BaseModel, ConfigDict


class SystemConfigPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    site_title: str | None = None
    site_logo_url: str | None = None
    smart_proto_enabled: str | None = None
    custom_proto_header: str | None = None
    default_user_points: str | None = None
    invite_bonus_points: str | None = None
    invite_reward_mode: str | None = None
    manual_grant_default_points: str | None = None
    redeem_code_default_points: str | None = None
    answer_retry_times: str | None = None
    image_generation_points: str | None = None
    image_generation_max_active_jobs: str | None = None
    image_generation_daily_limit: str | None = None
    image_generation_retention_days: str | None = None
    project_update_enabled: str | None = None
    project_update_auto_check_enabled: str | None = None
    project_update_check_interval_hours: str | None = None
    project_update_repository: str | None = None
    project_update_workflow: str | None = None
    project_update_github_token: str | None = None
    registration_enabled: str | None = None
    registration_email_mode: str | None = None
    email_verification_enabled: str | None = None
    smtp_host: str | None = None
    smtp_port: str | None = None
    smtp_security: str | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_from_name: str | None = None
    email_code_ttl_minutes: str | None = None
    email_code_cooldown_seconds: str | None = None
    email_code_daily_limit: str | None = None
    email_code_ip_hourly_limit: str | None = None
    email_code_max_attempts: str | None = None


class EmailDomainWhitelistPayload(BaseModel):
    """邮箱域名白名单整体替换请求。"""

    domains: list[str]


class ProjectUpdateApplyPayload(BaseModel):
    """触发 GitHub Actions 部署时确认的 Release 版本。"""

    expected_version: str
