# API Contract

Updated: `2026-07-24`

## 1. Purpose

This document defines the normalized internal API for the study assistant service. It is intentionally client-agnostic so the backend remains stable even if downstream tools or adapters change later.

## 2. Request Shape

### 2.1 Minimal request

```json
{
  "title": "1+2 = ?",
  "options": [
    "A. 1",
    "B. 2",
    "C. 3",
    "D. 4"
  ],
  "type": "single"
}
```

### 2.2 Extended request

```json
{
  "title": "1+2 = ?",
  "options": [
    "A. 1",
    "B. 2",
    "C. 3",
    "D. 4"
  ],
  "type": "single",
  "subject": "math",
  "source_context": "practice_set_a",
  "tags": ["arithmetic", "basic"],
  "locale": "zh-CN",
  "request_id": "demo-001"
}
```

## 3. Normalized Response Shape

```json
{
  "ok": true,
  "request_id": "demo-001",
  "query": {
    "title": "1+2 = ?",
    "type": "single",
    "options": ["A. 1", "B. 2", "C. 3", "D. 4"]
  },
  "result": {
    "candidate_answer": "C",
    "answer_text": "C. 3",
    "explanation": "The sum of 1 and 2 is 3.",
    "confidence": 0.99,
    "resolution_mode": "exact_match",
    "review_required": false
  },
  "sources": [
    {
      "source_name": "seed-curated-bank",
      "source_type": "qa_record",
      "source_id": "math-basic-0001",
      "source_url": null,
      "score": 0.998
    }
  ],
  "debug": {
    "trace_id": "trace-demo-001",
    "retrieval_strategy": "exact_then_hybrid",
    "provider": "local-normalized-jsonl"
  }
}
```

## 4. Error Response Shape

```json
{
  "ok": false,
  "request_id": "demo-001",
  "error": {
    "code": "INVALID_REQUEST",
    "message": "title is required"
  }
}
```

## 5. Field Rules

### Request fields

- `title`: required string
- `options`: optional array of strings; normalize string input into arrays during ingestion if needed
- `type`: required enum; initial values should be `single`, `multiple`, `judgement`, `completion`, `unknown`
- `subject`: optional string
- `source_context`: optional string
- `tags`: optional string array
- `locale`: optional string
- `request_id`: optional string

### Response fields

- `candidate_answer`: normalized symbolic answer such as `A`, `A#C`, `true`, or a completion string
- `answer_text`: answer rendered for human review
- `explanation`: concise rationale or retrieved explanation
- `confidence`: `0.0` to `1.0`
- `resolution_mode`: `exact_match`, `fuzzy_match`, `rag_match`, `external_source`, `llm_normalized`, `fallback`
- `review_required`: boolean

## 6. External Adapter Mapping Notes

The service should support a thin adapter layer that:

- converts incoming placeholders or foreign field names into the normalized request shape
- converts normalized responses into the downstream consumer format

Keep this adapter outside the core retrieval logic.

## 7. API Versioning And Health Endpoints

All business APIs use the canonical `/api/v1` prefix. The only business exception is the
OCS-compatible `/ocs/query` endpoint, whose path remains stable for imported clients.

- `GET /api/v1/healthz`
- `GET /api/v1/version`
- `GET /api/v1/status`
- `GET /api/v1/query?title=...&options=...&type=...`
- `POST /api/v1/query`
- `GET /ocs/query?title=...&options=...&type=...`
- `POST /ocs/query`

### Project update control plane

The following versioned endpoints are restricted to `superadmin` users with `system:write`.
They check a validated GitHub Release and dispatch a deployment workflow; they never run Docker
or SSH commands in the API process.

- `GET /api/v1/project-update/status`
- `POST /api/v1/project-update/check`
- `POST /api/v1/project-update/apply` with `{ "expected_version": "X.Y.Z" }`
- `GET /api/v1/project-update/operations/{operation_id}`
- `DELETE /api/v1/project-update/token`

The system configuration stores `project_update_enabled`,
`project_update_auto_check_enabled`, `project_update_check_interval_hours`,
`project_update_repository`, `project_update_workflow`, and a write-only
`project_update_github_token`. Automatic checks are limited to one check every 1 to 168 hours
and only discover verified releases; deployment always needs an explicit `apply` request. The
token is never included in API responses; a `project_update_github_token_configured` boolean is
returned instead. `DELETE /api/v1/project-update/token` clears the stored token only after the
update feature is disabled and no deployment task is active.

### `POST /api/v1/query` 单输入框请求

在线搜题可使用 `raw_text` 提交完整粘贴内容，服务端会在进入检索链路前解析题干和末尾选项：

```json
{
  "raw_text": "多选题：下列哪些属于示例？\nA. 选项一\nB、选项二\nC）选项三",
  "type": "multiple"
}
```

- `raw_text` 与结构化 `title`、`options` 互斥，混用返回 `400 INVALID_INPUT`。
- 仅识别至少两条连续的标准选项行，支持 `A.`、`A、`、`A）`、`(A)` 等标签；无法确认时完整保留原文作为题干。
- 未传 `type` 时，仅从明确题型标记自动识别；不会根据选项数量猜测单选或多选。
- 既有 `title`、`options`、`type` 请求和 OCS `/ocs/query` 契约保持不变。

OpenAPI UI is available at `/api/docs`; the schema is served from
`/api/v1/openapi.json`. Legacy unversioned business routes remain temporarily callable,
are hidden from OpenAPI, and return `Deprecation: true` plus a successor `Link` header.

Suggested runtime status response:

```json
{
  "llm": {
    "provider": "openai-compatible",
    "healthy": true
  },
  "embedding": {
    "provider": "openai-compatible",
    "healthy": true
  },
  "retrieval": {
    "provider": "local-normalized-jsonl",
    "healthy": true
  }
}
```

## 8. Validation Rules For Version 1

- reject empty `title`
- coerce `options` strings into arrays only in adapter or ingestion layers
- reject unsupported question types unless explicitly mapped to `unknown`
- always return at least one provenance field when `ok` is true
- mark `review_required` as true when confidence is below threshold or when no curated source was used

## 9. Current Local Implementation

The current local implementation is documented in [local-service.md](../docs/local-service.md).

Current behavior:

- normalized JSONL index
- exact match first
- fuzzy match fallback
- optional OpenAI-compatible model fallback
- provenance required for successful responses
- no external model provider required by default

## 10. Image Generation

文本生图是独立于查题与 OCS 图片资源的私有功能。它支持 Gemini 原生、OpenAI Images 和受控
兼容 Images 协议，并且不会复用题目 `usage_logs` 或 OCS 公共图床。

### User endpoints

- `GET /api/v1/image-generation-capabilities`
- `POST /api/v1/image-generations`
- `GET /api/v1/image-generations`
- `GET /api/v1/image-generations/{job_id}`
- `GET /api/v1/image-generations/{job_id}/assets/{asset_id}/content`
- `DELETE /api/v1/image-generations/{job_id}`

创建请求示例：

```json
{
  "prompt": "雨后城市街道，水彩插画风格，暖色灯光",
  "output": {
    "aspect_ratio": "16:9",
    "image_size": "2K"
  },
  "idempotency_key": "optional-client-key"
}
```

`output` 由当前启用模型的输出能力决定：Gemini 使用 `aspect_ratio` 与 `image_size`；OpenAI Images
与通用兼容协议使用 `{ "size": "宽x高" }`。旧 `size` 字段仍兼容，但不能与非空 `output` 同时提交。
旧聊天生图模型不接受尺寸控制，任务会显示“由模型决定”。任务响应中的 `output` 是归一化请求参数，
生成资产的 `width` 与 `height` 是实际输出尺寸。

`Idempotency-Key` 请求头优先于请求体字段。创建成功时返回 `202`；相同用户和幂等键
重复提交时返回原任务和 `idempotent_replay: true`，不会重复预扣积分。

任务状态为 `queued`、`running`、`succeeded`、`failed`、`rejected`、`cancelled` 或
`deleted`。提交时预扣单张积分，成功保存至少一个合格资产后确认扣费；模型拒绝、超时、
下载或图片校验失败时自动退款。系统不会对已经提交给供应商的任务自动重试或切换模型，
用户需要显式创建新的任务。

资产内容接口必须携带登录 JWT。所有者和管理员可以读取，其他用户返回 `403`；响应携带
`Cache-Control: private, no-store`，不提供第三方图片 URL 或公开直链。

### Management endpoints

- `GET|POST /api/v1/image-generation-models`
- `PATCH|DELETE /api/v1/image-generation-models/{model_id}`
- `POST /api/v1/image-generation-models/{model_id}/test`
- `GET /api/v1/image-generation-stats`
- `GET /api/v1/image-generation-traces`

模型配置支持 `gemini-native`（`generateContent`）、`openai-images`（`/images/generations`）、
`openai-compatible-images`（受控兼容 `/images/generations`）和旧 `openai-chat-image`（聊天补全返回图片）。
`protocol_config` 是受严格校验的结构化能力声明：Gemini 声明鉴权方式、画幅与像素档位；OpenAI 原生可
声明预设尺寸与自定义尺寸约束；通用兼容协议仅声明预设尺寸。`api_key` 只接受写入，任何读取接口只返回
`api_key_configured`；调用追溯不保存提示词、图片字节、Base64 或供应商密钥。首版同一时间
仅有一个可用于新任务的启用模型，启用新模型会停用之前的模型，避免请求被隐式分流。

系统配置的 `image_generation_points`、`image_generation_max_active_jobs`、
`image_generation_daily_limit` 和 `image_generation_retention_days` 控制计费、限流和保留期。
保留期为 `0` 表示永久保留；其他值按天计算，过期资产会撤销访问并清理本地文件。

