# 生图与图片编辑 API

标准前缀：`/api/v1`。

- 任务、能力和私有资产接口要求登录及 `image-generation:use`。
- 模型、统计和追踪接口要求 `llm:read`；模型写入和测试要求 `llm:write`。
- 私有图片响应使用 `Cache-Control: private, no-store`，不会生成公开直链。
- 生图领域错误使用统一错误对象；具体错误码以服务端返回为准。

## 能力与任务

| 方法 | 路径 | 权限 | 请求参数 | 成功响应 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/image-generation-capabilities` | `image-generation:use` | 无 | `{ok,capabilities}` |
| `POST` | `/api/v1/image-generation-infer-size` | `image-generation:use` | JSON：`{prompt: string}` | `{ok,output,explanation}` |
| `POST` | `/api/v1/image-generations` | `image-generation:use` | JSON：见 `ImageGenerationCreatePayload`；可用 `Idempotency-Key` 请求头 | 新建 `202 {ok,job,idempotent_replay:false}`；幂等重放 `200 {ok,job,idempotent_replay:true}` |
| `GET` | `/api/v1/image-generations` | `image-generation:use`；按 `user_id` 跨用户查询需 `llm:read` | Query：`status`、`page`（默认 `1`）、`limit`（默认 `30`，上限 `100`）、`user_id` | `{ok,jobs,total,page,limit}` |
| `GET` | `/api/v1/image-generations/{job_id}` | `image-generation:use` | Path：`job_id` | `{ok,job}` |
| `DELETE` | `/api/v1/image-generations/{job_id}` | `image-generation:use` | Path：`job_id` | `{ok,job}` |

### `ImageGenerationCreatePayload`

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `prompt` | `string` | `""` | 提示词 |
| `size` | `string` | `""` | 输出尺寸；空值由服务端或模型决定 |
| `mode` | `string` | `text_to_image` | `text_to_image`、`image_edit`、`masked_edit`、`multi_reference` |
| `input_assets` | `array[ImageGenerationInputReferencePayload]` | `[]` | 输入图片引用 |
| `output` | `object` | `null` | 输出配置 |
| `idempotency_key` | `string` | `""` | 幂等键；请求头 `Idempotency-Key` 优先 |

### `ImageGenerationInputReferencePayload`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `source_kind` | `string` | `uploaded` 或 `generated` |
| `source_id` | `string` | 输入资产 ID |
| `source_job_id` | `string` | 历史生成任务 ID；默认空字符串 |
| `role` | `string` | `source`、`reference` 或 `mask` |

## 私有输入与输出资产

| 方法 | 路径 | 权限 | 请求参数 | 成功响应 |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/image-generation-inputs` | `image-generation:use` | `multipart/form-data`：文件字段 `image`；Query：`kind`（默认 `source`） | `201 {ok,asset}` |
| `GET` | `/api/v1/image-generation-inputs` | `image-generation:use` | Query：`page`（默认 `1`）、`limit`（默认 `60`，上限 `100`） | `{ok,assets,total,page,limit}` |
| `GET` | `/api/v1/image-generation-inputs/{input_id}/content` | `image-generation:use`；管理员跨用户需 `llm:read` | Path：`input_id` | 原始图片二进制；私有、禁止缓存 |
| `DELETE` | `/api/v1/image-generation-inputs/{input_id}` | `image-generation:use`；管理员跨用户需 `llm:read` | Path：`input_id` | `{ok,asset}` |
| `GET` | `/api/v1/image-generations/{job_id}/assets/{asset_id}/content` | `image-generation:use`；管理员跨用户需 `llm:read` | Path：`job_id`、`asset_id` | 原始图片二进制；私有、禁止缓存 |

## 模型管理与运维

| 方法 | 路径 | 权限 | 请求参数 | 成功响应 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/image-generation-models` | `llm:read` | 无 | `{ok,models}`；密钥脱敏 |
| `POST` | `/api/v1/image-generation-models` | `llm:write` | JSON：见 `ImageGenerationModelCreatePayload` | `201 {ok,model}` |
| `PATCH` | `/api/v1/image-generation-models/{model_id}` | `llm:write` | Path：`model_id`；JSON：更新字段 | `{ok,model}` |
| `DELETE` | `/api/v1/image-generation-models/{model_id}` | `llm:write` | Path：`model_id` | `{ok}` |
| `POST` | `/api/v1/image-generation-models/{model_id}/test` | `llm:write` | Path：`model_id`；JSON 可选 `operation` | 成功：`{ok:true,operation,elapsed_ms,provider_request_id}`；失败：`{ok:false,operation,elapsed_ms,error_code,error}` |
| `GET` | `/api/v1/image-generation-stats` | `llm:read` | 无 | `{ok,stats}` |
| `GET` | `/api/v1/image-generation-traces` | `llm:read` | Query：`job_id`、`model_id`、`page`（默认 `1`）、`limit`（默认 `100`，上限 `500`） | `{ok,traces,total,page,limit}`；不含提示词和密钥 |

### `ImageGenerationModelCreatePayload`

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `string` | `""` | 展示名称 |
| `provider` | `string` | `openai-images` | 提供商类型 |
| `base_url` | `string` | `""` | 服务端点 |
| `model` | `string` | `""` | 模型标识 |
| `api_key` | `string` | `""` | 服务密钥 |
| `timeout_seconds` | `number` | `60` | 超时秒数 |
| `status` | `string` | `active` | 配置状态 |
| `capabilities` | `array[string]` | `[]` | 支持的能力列表 |
| `protocol_config` | `object` | `null` | 协议扩展配置 |

`ImageGenerationModelUpdatePayload` 字段全部可选。`operation` 可取 `text_to_image`、`whole_edit`、`masked_edit`、`multi_reference`，默认 `text_to_image`。
