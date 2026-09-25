# Token、角色与权限 API

规范前缀：`/api/v1`。

## 1. API Token

Token 资源接口均要求当前用户登录；资源所有权由服务端校验。当前路由以登录态作为运行时门禁，`tokens:self` 仅作为权限目录和角色标识，不在这些路由中单独执行权限拒绝。

| 方法 | 路径 | 请求 | 成功响应 | 说明 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/tokens` | 无 | `tokens` | 列出当前用户 Token |
| `POST` | `/api/v1/tokens` | `TokenCreatePayload` | `token`、`token_info`、`ocs_config` | 创建；敏感值仅在必要响应中返回，响应 `no-store` |
| `POST` | `/api/v1/tokens/{token_id}/revoke` | path `token_id` | `token` | 撤销 Token |
| `POST` | `/api/v1/tokens/{token_id}` | path + `TokenUpdatePayload` | `token` | 更新 Token |
| `DELETE` | `/api/v1/tokens/{token_id}` | path `token_id` | `message` | 删除 Token |
| `GET` | `/api/v1/tokens/import-script` | `token_id?`、`template_id?`（query） | 脚本和配置 | 生成/读取 Token 对应导入脚本；`no-store` |
| `POST` | `/api/v1/tokens/{token_id}/copy-value` | path `token_id` | `token_id`、一次性 `token` | 复制 Token 值；`no-store` |
| `POST` | `/api/v1/tokens/{token_id}/share-link` | path `token_id` | 分享信息 | 创建 Token 分享链接；`no-store` |

### 请求模型

| 模型 | 字段 |
| --- | --- |
| `TokenCreatePayload` | `description: string = ""`、`quota_limit: integer = -1`、`reject_low_confidence: boolean = false`、`min_answer_confidence: number = 0`、`bind_client: boolean = false` |
| `TokenUpdatePayload` | `description?`、`quota_limit?`、`reject_low_confidence?`、`min_answer_confidence?`、`bind_client?`、`reset_bound_client: boolean = false` |

常见错误包括未认证、权限不足、资源不存在和状态冲突；具体业务错误码以服务端返回为准。调用方必须将 Token 视为密码处理。

## 2. 角色目录与权限

| 方法 | 路径 | 权限 | 请求 | 成功响应 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/roles` | `roles:read` | 无 | `roles`、`permission_catalog` |
| `GET` | `/api/v1/roles/{role_id}` | `roles:read` | path `role_id` | `role` |
| `GET` | `/api/v1/roles/{role_id}/permissions` | `roles:read` | path `role_id` | `{ok,role}` |
| `POST` | `/api/v1/roles` | `roles:write` + `superadmin` | `RoleCreatePayload` | `201`，`role` |
| `PATCH` | `/api/v1/roles/{role_id}` | `roles:write` | path + `RoleUpdatePayload` | `role` |
| `PUT` | `/api/v1/roles/{role_id}/permissions` | `roles:write` | path + `RolePermissionPayload` | `role` |
| `DELETE` | `/api/v1/roles/{role_id}` | `roles:write` + `superadmin` | path `role_id` | `role_id`、`deleted: true` |

| 模型 | 字段 |
| --- | --- |
| `RoleCreatePayload` | `role_id: string`、`name: string`、`description: string`、`permissions: string[]` |
| `RoleUpdatePayload` | `name?`、`description?`、`permissions?: string[]` |
| `RolePermissionPayload` | `permissions: string[]` |

系统角色、正在使用中的角色或不存在角色的删除由服务端拒绝，并返回结构化业务错误。

## 3. API Key 配置模板

### `GET /api/v1/shares/apikey-template`

公开接口，返回用于外部脚本接入的模板：

```json
{
  "ok": true,
  "template_id": "...",
  "script": "...",
  "ocs_config": []
}
```

响应允许公开缓存 300 秒。模板中的占位符由客户端或管理端在使用时替换，实际 Token 不应写入模板。
