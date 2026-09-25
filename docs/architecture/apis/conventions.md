# API 通用约定

## 1. 基础地址与版本

以部署域名为 `{base_url}`：

```text
规范 API：{base_url}/api/v1
OCS 兼容：{base_url}/ocs/query
```

规范业务路由统一使用 `/api/v1`。应用同时挂载一组无前缀旧路径；该组路径不进入 OpenAPI，响应包含：

```http
Deprecation: true
Link: </api/v1/{same-path}>; rel="successor-version"
```

旧路径仅用于兼容，新的客户端不得依赖该路径。

## 2. 请求约定

| 项目 | 约定 |
| --- | --- |
| JSON 请求 | `Content-Type: application/json` |
| 文件上传 | `multipart/form-data` |
| JSON 响应 | `Accept: application/json` |
| 登录态 | `stqb_session` Cookie，或 `Authorization: Bearer <token>` |
| OCS 调用 | `Authorization: Bearer <API Key>`；启用全局鉴权时可使用静态 OCS Key 或绑定用户的有效 API Token |
| 生图幂等 | `POST /api/v1/image-generations` 支持 `Idempotency-Key` 请求头；也可使用请求体 `idempotency_key` |
| 字符编码 | UTF-8 |

参数来源在领域文档中标注为 `path`、`query`、`header`、`body` 或 `multipart`。除特别说明外，字符串缺省值为空字符串，列表缺省为空列表。

## 3. 鉴权与权限

### 3.1 鉴权方式

- `public`：无需登录。
- `session`：需要登录用户；可使用会话 Cookie 或用户 Token。
- `ocs-key`：需要 OCS 静态 API Key 或绑定到用户的有效 API Token；关闭全局鉴权时无需 Key。
- `permission:<name>`：需要登录，并具备指定权限；`superadmin` 绕过权限集合校验。

启用全局鉴权时，查题、状态和诊断接口受保护；未启用时仍建议在生产环境配置鉴权。

### 3.2 当前权限名

| 权限 | 用途 |
| --- | --- |
| `users:write` | 用户管理 |
| `tokens:self` | 当前用户的 API Token 管理 |
| `roles:read` / `roles:write` | 角色与权限管理 |
| `questions:read` / `questions:write` | 题库读取和维护 |
| `feedback:self` / `feedback:manage` | 提交反馈和处理反馈 |
| `wallet:changes:read` / `wallet:changes:write` | 钱包流水、权益和兑换码管理 |
| `billing:read` / `billing:write` | 计费配置 |
| `dashboard:all` | 查看全局日志和看板数据 |
| `dashboard:self` | 查看个人看板数据 |
| `system:read` / `system:write` | 诊断、配置、日志和更新 |
| `import-scripts:read` / `import-scripts:write` | 导入脚本管理 |
| `llm:read` / `llm:write` | 大模型配置和调用追溯 |
| `image-generation:use` | 使用生图能力 |
| `announcements:read` / `announcements:write` | 公告读取和管理 |

## 4. 成功响应

项目采用资源字段包裹的 JSON 响应，典型结构如下：

```json
{
  "ok": true,
  "user": {},
  "page": 1,
  "limit": 50,
  "total": 0
}
```

具体资源字段（例如 `query` 的 `result`、`tokens`、`job`、`feedbacks`）以各领域文档为准。二进制媒体接口直接返回文件，不使用 JSON 包装。

## 5. 错误响应

业务错误统一使用：

```json
{
  "ok": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "可供调用方处理的错误说明"
  }
}
```

常见 HTTP 状态码：

| 状态码 | 语义 |
| ---: | --- |
| `200` | 成功读取、更新或动作完成 |
| `201` | 成功创建资源 |
| `202` | 异步任务已接受；例如生图任务创建 |
| `204` | CORS 预检成功，无响应体 |
| `400` | 参数、业务状态或日期格式无效 |
| `401` | 未认证、会话失效或 API Key 无效 |
| `402` | 余额或积分不足 |
| `403` | 已认证但权限不足 |
| `404` | 资源不存在 |
| `409` | 状态冲突、重复资源或幂等冲突 |
| `422` | FastAPI 请求校验失败 |
| `429` | 频率、额度或发送限制 |
| `500` | 未处理服务错误；细节只写入服务端日志 |

`422` 的校验响应由 FastAPI 生成，常见结构为 `{"detail":[{"loc":[],"msg":"...","type":"..."}]}`。调用方应优先处理 `error.code`，而不是匹配展示文案。

## 6. 分页与筛选

分页接口通常接受：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | ---: | --- |
| `page` | integer | `1` | 从 1 开始 |
| `limit` | integer | 领域默认值 | 服务端会限制最大值 |

分页响应通常返回 `page`、`limit`、`total` 和资源数组。日期参数使用 `YYYY-MM-DD`；开始日期不得晚于结束日期。

## 7. 安全与兼容

- 不在请求日志、示例或客户端持久化中记录密码、API Key、模型密钥和完整敏感令牌。
- 公开媒体和私有生图资产的访问规则不同；私有资产必须通过登录态访问，响应设置 `Cache-Control: private, no-store`。
- `/ocs/query` 是稳定的外部适配入口，返回 OCS `code/data` 契约；标准 `/api/v1/query` 返回平台标准结果。
- `/feedback/answer-records` 仅为反馈表单提供历史作答关联选项，不是答题接口。
