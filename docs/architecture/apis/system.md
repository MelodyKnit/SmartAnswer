# 系统配置、日志与帮助 API

标准前缀：`/api/v1`。系统配置、更新和日志接口为管理接口；站点配置、帮助文档和部分公共资源可匿名访问。

## 系统配置与更新

| 方法 | 路径 | 权限 | 请求参数 | 成功响应 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/system-config` | `system:write` | 无 | `{ok,config}` |
| `PATCH` | `/api/v1/system-config` | `system:write` | JSON：见 `SystemConfigPayload` | `{ok,config,reload_required:false}` |
| `GET` | `/api/v1/site-config` | 公开 | 无 | `{ok,...site_config}`；`site_config` 字段随配置项变化 |
| `GET` | `/api/v1/system/email-domain-whitelist` | `system:write` | 无 | `{ok,domains}` |
| `PUT` | `/api/v1/system/email-domain-whitelist` | `system:write` | JSON：`{domains: string[]}` | `{ok,domains}` |
| `GET` | `/api/v1/project-update/status` | `system:write` | 无 | `{ok,update}` |
| `POST` | `/api/v1/project-update/check` | `system:write` | 无 | `{ok,update}` |
| `POST` | `/api/v1/system/logo/upload` | `system:write` | `multipart/form-data`：文件字段 `file`，必须为图片且不超过 5 MB | `{ok,urls,config}` |

### `SystemConfigPayload`

所有字段可选，类型均为 `string`；仅更新实际传入的字段。

| 配置域 | 字段 |
| --- | --- |
| 站点与协议 | `site_title`、`site_logo_url`、`smart_proto_enabled`、`custom_proto_header` |
| 积分与邀请 | `default_user_points`、`invite_bonus_points`、`invite_reward_mode`、`manual_grant_default_points`、`redeem_code_default_points` |
| 答题与生图 | `answer_retry_times`、`image_generation_points`、`image_generation_max_active_jobs`、`image_generation_daily_limit`、`image_generation_retention_days` |
| 认证与注册 | `registration_enabled`、`registration_captcha_enabled`、`login_captcha_enabled`、`login_failure_threshold`、`registration_email_mode`、`email_verification_enabled` |
| SMTP | `smtp_host`、`smtp_port`、`smtp_security`、`smtp_username`、`smtp_password`、`smtp_from_email`、`smtp_from_name` |
| 邮箱验证码 | `email_code_ttl_minutes`、`email_code_cooldown_seconds`、`email_code_daily_limit`、`email_code_ip_hourly_limit`、`email_code_max_attempts` |
| 日志 | `log_retention_days`、`log_max_size_mb` |

## 日志

| 方法 | 路径 | 权限 | 请求参数 | 成功响应 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/system/logs/stats` | `system:read` | 无 | `{ok,...stats}`；统计字段由日志实现提供 |
| `POST` | `/api/v1/system/logs/cleanup` | `system:write` | JSON：见 `LogCleanupPayload` | `{ok,...cleanup_result,stats}`；清理结果字段由日志实现提供 |
| `GET` | `/api/v1/system/logs/console` | `system:read` | Query：`limit`（默认 `500`，最大 `2000`）、`offset`（默认 `0`） | `{ok,logs}` |
| `POST` | `/api/v1/system/logs/console/clear` | `system:write` | 无 | `{ok}` |

### `LogCleanupPayload`

| 字段 | 类型 | 默认值 | 约束与说明 |
| --- | --- | --- | --- |
| `mode` | `string` | `days` | `days`、`files` 或 `all` |
| `days` | `integer` | `null` | `1` 至 `3650`；`days` 模式默认 `30` |
| `keep_files` | `integer` | `null` | `1` 至 `10000`；`files` 模式默认保留 `10` 个 |

## 帮助文档

| 方法 | 路径 | 权限 | 请求参数 | 成功响应 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/help/docs` | 公开 | 无 | `{docs:[{id,title,category,icon,order,description,content}]}` |

帮助内容由服务端文档目录生成，不保证包含 `ok` 字段。
