# API 文档

本目录是 StudyQuestionBankAssistant HTTP API 的按领域接口参考。接口定义以运行时代码和 FastAPI OpenAPI 输出为准；本文档用于快速定位资源、请求约定和调用边界。

## 版本与统计

| 范围 | 数量 | 说明 |
| --- | ---: | --- |
| `/api/v1` 规范业务操作 | 124 | 19 个业务领域路由的公开规范版本 |
| `/ocs/query` 兼容操作 | 2 | `GET`、`POST`，不使用 `/api/v1` 前缀 |
| 规范业务操作合计 | 126 | 本目录按此口径编排 |
| 无前缀旧路径 | 124 | 与 v1 共用实现，隐藏于 OpenAPI，返回弃用响应头，不重复展开 |

## 文档索引

| 文档 | 覆盖范围 | 操作数 |
| --- | --- | ---: |
| [conventions.md](conventions.md) | 基础 URL、版本、鉴权、通用响应、错误、分页、权限和兼容规则 | - |
| [query.md](query.md) | 健康检查、查题、OCS 兼容、诊断、OCS 配置 | 10 |
| [auth-users.md](auth-users.md) | 注册、登录、会话、密码、用户资料和用户管理 | 17 |
| [access-control.md](access-control.md) | API Token、角色权限、Token 脚本和分享 | 16 |
| [questions-media.md](questions-media.md) | 题库管理、题目索引、媒体和图片代理 | 7 |
| [usage-feedback-dashboard.md](usage-feedback-dashboard.md) | 使用日志、反馈、反馈关联记录和工作台 | 8 |
| [wallet.md](wallet.md) | 钱包、计费、积分、权益发放和兑换码 | 12 |
| [notifications-announcements.md](notifications-announcements.md) | 通知中心和公告 | 11 |
| [imports-llm.md](imports-llm.md) | 导入脚本、大模型配置、调用统计和追溯 | 14 |
| [image-generation.md](image-generation.md) | 生图能力、任务、私有输入资产、模型和追溯 | 18 |
| [system.md](system.md) | 系统配置、站点配置、域名白名单、更新、日志、帮助文档 | 13 |

## 路由入口

| 入口 | 用途 |
| --- | --- |
| `GET /api/docs` | Swagger UI |
| `GET /api/v1/openapi.json` | OpenAPI 3 JSON |
| `GET /{path:path}` | 前端静态资源和 SPA 回退；不属于业务 API |
| `HEAD /{path:path}` | 前端静态资源和 SPA 回退；不属于业务 API |
| `OPTIONS <任意路径>` | CORS 预检，由 HTTP 中间件统一处理，返回 `204` |

## 阅读与维护约定

1. 领域文档中的规范路径均包含 `/api/v1`；请求参数、请求体、成功响应、错误响应和权限要求按接口逐项列出。
2. 请求体字段以代码中的 Pydantic 模型为准。未列出的额外字段通常会被忽略，但调用方不应依赖该兼容行为。
3. 通用字段、状态码、分页、鉴权和旧路径规则只在 [conventions.md](conventions.md) 维护；领域文档只记录差异。
4. 旧无前缀路径复用相同的 v1 路由，例如 `/query` 是 `/api/v1/query` 的兼容别名；调用方应迁移到规范路径。
5. 详细响应字段以当前部署的 OpenAPI 文档和接口实现为最终依据。敏感值（API Key、模型密钥、密码）不应出现在日志、示例或文档中。

## 相关文档

- [系统架构](../architecture.md)
- [本地服务](../../services/local-service.md)
- [OCS 适配](../../services/ocs-adapter.md)
- [项目文档导航](../../README.md)
