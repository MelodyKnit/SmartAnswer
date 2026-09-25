# 认证与用户 API

规范前缀：`/api/v1`。

## 1. 认证与会话

| 方法 | 路径 | 认证/权限 | 请求 | 成功响应 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/auth/session` | `session` | 无 | 当前会话用户；未登录返回 `401` |
| `GET` | `/api/v1/auth/captcha/slider` | `public` | 无 | 滑块挑战信息 |
| `POST` | `/api/v1/auth/captcha/slider/verify` | `public` | `SliderVerifyPayload` | 验证结果/挑战令牌 |
| `POST` | `/api/v1/auth/register` | `public` | `RegisterPayload` | `{"ok": true, "user": {...}}` |
| `POST` | `/api/v1/auth/email-verification-codes` | `public` | `EmailVerificationCodePayload` | 发送结果 |
| `GET` | `/api/v1/auth/register-status` | `public` | 无 | 注册开关、验证码和邮箱策略 |
| `POST` | `/api/v1/auth/login` | `public` | `LoginPayload` | `{"ok": true, "user": {...}, "token": "...", "expires_in": 3600}` |
| `POST` | `/api/v1/auth/logout` | 可匿名调用；有会话时注销 | 无 | `{"ok": true}` |
| `POST` | `/api/v1/auth/reset-request` | `public` | `ResetRequestPayload` | 重置请求结果 |
| `POST` | `/api/v1/auth/reset-confirm` | `public` | `ResetConfirmPayload` | 密码重置结果 |

### 请求体

| 模型 | 字段（类型） | 说明 |
| --- | --- | --- |
| `SliderVerifyPayload` | `challenge_id: string`、`x: number` | 滑块挑战 ID 和滑动位置 |
| `RegisterPayload` | `username: string`、`password: string`、`email?: string`、`email_code?: string`、`invite_code?: string`、`captcha_token?: string` | 注册信息；是否必需邮箱、邀请码和验证码由站点配置决定 |
| `EmailVerificationCodePayload` | `email: string`、`purpose?: string` | 验证码用途默认 `register` |
| `LoginPayload` | `username: string`、`password: string`、`remember?: boolean`、`captcha_token?: string` | 登录凭据和记住登录选项 |
| `ResetRequestPayload` | `username: string` | 账号或用户名 |
| `ResetConfirmPayload` | `username: string`、`token: string`、`new_password: string` | 重置凭据 |

常见错误：`REGISTRATION_DISABLED`、`BAD_CREDENTIALS`、`CAPTCHA_REQUIRED`、`CAPTCHA_INVALID`、`EMAIL_CODE_INVALID`、`USERNAME_TAKEN`、`INVALID_RESET_TOKEN`。

## 2. 当前用户

| 方法 | 路径 | 认证/权限 | 请求 | 成功响应 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/users/me` | `session` | 无 | `{"ok": true, "user": {...}, "billing": {...}, "wallet": {...}}` |
| `PATCH` | `/api/v1/users/me/profile` | `session` | `ProfileUpdatePayload` | `{"ok": true, "user": {...}}` |
| `POST` | `/api/v1/users/me/invite-code` | `session` | 无 | `{"ok": true, "user": {...}}` |
| `POST` | `/api/v1/users/me/password` | `session` | `PasswordChangePayload` | `{"ok": true, "message": "..."}` |

| 模型 | 字段（类型） |
| --- | --- |
| `ProfileUpdatePayload` | `display_name?: string`、`email?: string` |
| `PasswordChangePayload` | `old_password: string`、`new_password: string` |

当前个人资料路由仅持久化 `display_name`；`email` 字段会被模型接收，但不会在该路由中更新。

## 3. 用户管理

| 方法 | 路径 | 认证/权限 | 请求 | 成功响应 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/users` | `users:write` | 无 | `{ok,users}` |
| `PATCH` | `/api/v1/users/{username}` | `users:write` | Path：`username`；JSON：`UserUpdatePayload` | `{ok,user}` |
| `POST` | `/api/v1/users/batch-delete` | `users:write` | JSON：`UsersDeletePayload` | `{ok,deleted,skipped}` |

`UserUpdatePayload` 字段：`role?: string`、`points?: integer`、`status?: string`、`unlimited_expires_at?: number`。`UsersDeletePayload` 字段：`usernames: string[]`。

用户管理接口返回用户集合或更新后的用户资源；不存在用户返回 `404 USER_NOT_FOUND`，禁止删除受保护的内置用户时返回业务错误。
