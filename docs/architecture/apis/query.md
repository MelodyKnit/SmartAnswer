# 查询与诊断 API

规范前缀：`/api/v1`。本文件覆盖查询路由中的 8 个规范操作，以及 OCS 兼容路由的 2 个操作。

## 1. 健康、版本与状态

| 方法 | 路径 | 认证/权限 | 请求 | 成功响应 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/healthz` | `public` | 无 | `{"ok": true}` |
| `GET` | `/api/v1/version` | `public` | 无 | `ok`、`version`、构建信息 |
| `GET` | `/api/v1/status` | 鉴权启用时 `session` | 无 | 服务状态、索引和运行时信息 |
| `GET` | `/api/v1/debug/recent` | `system:read` | `start_date`、`end_date`（query，可选） | `{"ok": true, "events": [...]}` |
| `GET` | `/api/v1/debug/usage-audit` | `system:read` | `date`（query，可选） | `{"ok": true, "audit": {...}}` |
| `GET` | `/api/v1/configs/ocs-local-study-bank.json` | `public` | 无 | OCS 源配置 JSON |

日期格式为 `YYYY-MM-DD`。日期无效或开始日期晚于结束日期时返回 `400 INVALID_DATE`。

## 2. 标准查题

### `GET /api/v1/query`

同步执行本地题库检索、AI 兜底和可选联网增强。

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `title` | query | string | 否 | 题干；未提供有效题干时由服务返回输入错误 |
| `options` | query | string | 否 | 选项，支持约定的分隔格式 |
| `type` | query | string | 否 | 题型；别名映射为内部 `question_type` |
| `request_id` | query | string | 否 | 调用方追踪 ID |
| `image_urls` | query | string | 否 | 图片 URL 列表的兼容输入 |

成功返回标准查询结果：

```json
{
  "ok": true,
  "request_id": "req-123",
  "query": {
    "title": "壁胸膜的分部不包括",
    "type": "single_choice",
    "options": ["A", "B"]
  },
  "result": {
    "candidate_answer": "B",
    "answer_text": "肺胸膜",
    "explanation": "...",
    "confidence": 0.98,
    "review_required": false,
    "resolution_mode": "local"
  },
  "sources": [],
  "debug": {}
}
```

### `POST /api/v1/query`

`Content-Type: application/json`。请求体 `QueryPayload`：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `raw_text` | string | 否 | 在线搜题单输入框原文；与显式 `title`、`options` 互斥 |
| `title` | string | 否 | 题干 |
| `options` | string \| string[] | 否 | 选项 |
| `type` / `question_type` | string | 否 | 题型标识 |
| `request_id` | string | 否 | 请求追踪 ID |
| `page_url` | string | 否 | 来源页面 |
| `image_capture_status` | string | 否 | 图片采集状态 |
| `image_capture_failures` | integer | 否 | 图片采集失败次数 |
| `image_urls` | string[] | 否 | 题干图片 URL |
| `image_data_urls` | string[] | 否 | 题干图片 Data URL |
| `option_image_urls` | object | 否 | 选项标签到图片 URL 的映射 |
| `option_image_data_urls` | object | 否 | 选项标签到图片 Data URL 的映射 |

字段冲突、无法解析原文或题干为空时返回 `400 INVALID_INPUT`。成功响应与 `GET` 相同。

## 3. OCS 兼容查询

OCS 路由不使用 `/api/v1` 前缀，响应转换为 OCS 兼容的 `code/data` 结构。

### `GET /ocs/query`

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `title` | query | string | 否 | 题干 |
| `options` | query | string | 否 | OCS 选项字符串 |
| `type` | query | string | 否 | 题型 |
| `request_id` | query | string | 否 | 请求追踪 ID |
| `image_urls` | query | string | 否 | 图片 URL 兼容输入 |

### `POST /ocs/query`

`Content-Type: application/json`，请求体复用 `QueryPayload`。OCS 适配层负责字段解析和响应格式化。

成功示例：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "question": "壁胸膜的分部不包括",
    "answer": "B",
    "answer_text": "肺胸膜",
    "explanation": "...",
    "ai": {
      "review_required": false
    }
  }
}
```

失败时 `code` 非零，`data.answer` 可为空；鉴权失败、积分不足和低置信度拒答仍使用 HTTP 错误状态或 OCS 兼容错误数据。
