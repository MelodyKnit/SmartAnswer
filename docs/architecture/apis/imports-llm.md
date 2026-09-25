# 导入脚本与大模型 API

标准前缀：`/api/v1`。大模型配置和导入脚本管理接口均使用显式权限。请求中的密钥字段仅用于服务端配置，不应写入日志、文档或客户端代码。

## 导入脚本

| 方法 | 路径 | 权限 | 请求参数 | 成功响应 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/import-scripts` | `import-scripts:read` | 无 | `{ok,scripts}` |
| `POST` | `/api/v1/import-scripts` | `import-scripts:write` | JSON：见 `ImportScriptCreatePayload` | `{ok,script}` |
| `POST` | `/api/v1/import-scripts/generate` | `import-scripts:write` | JSON：见 `ImportScriptGeneratePayload` | `{ok,script}` |
| `GET` | `/api/v1/import-scripts/{script_id}` | `import-scripts:read` | Path：`script_id` | `{ok,script}` |
| `DELETE` | `/api/v1/import-scripts/{script_id}` | `import-scripts:write` | Path：`script_id` | `{ok}` |

### `ImportScriptGeneratePayload`

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `name` | `string` | 否 | `""` | 脚本名称 |
| `token_id` | `string` | 否 | `null` | 关联令牌 |
| `target` | `string` | 否 | `ocs` | 目标客户端或协议 |
| `include_test_snippet` | `boolean` | 否 | `true` | 是否包含测试片段 |

### `ImportScriptCreatePayload`

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `name` | `string` | 否 | `""` | 脚本名称 |
| `target` | `string` | 否 | `ocs` | 目标客户端或协议 |
| `description` | `string` | 否 | `""` | 描述 |
| `script_template` | `string` | 否 | `""` | 脚本模板标识或内容 |
| `content` | `string` | 否 | `""` | 脚本内容 |
| `config_items` | `array[object]` | 否 | `[]` | 配置项 |
| `requires_token` | `boolean` | 否 | `true` | 是否需要令牌 |
| `tags` | `array[string]` | 否 | `[]` | 标签 |
| `is_default` | `boolean` | 否 | `false` | 是否默认模板 |
| `status` | `string` | 否 | `active` | 状态 |

当前创建路由实际使用 `script_template` 生成内容；模型中的 `content` 和 `status` 字段会被接收但不会传入服务层，分别不改变生成内容和状态。

## 大模型配置

| 方法 | 路径 | 权限 | 请求参数 | 成功响应 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/llm-models` | `llm:read` | 无 | `{ok,models}` |
| `POST` | `/api/v1/llm-models` | `llm:write` | JSON：见 `LlmModelCreatePayload` | `{ok,model}` |
| `PATCH` | `/api/v1/llm-models/{model_id}` | `llm:write` | Path：`model_id`；JSON：`LlmModelUpdatePayload` | `{ok,model}` |
| `DELETE` | `/api/v1/llm-models/{model_id}` | `llm:write` | Path：`model_id` | `{ok}` |
| `POST` | `/api/v1/llm-models/{model_id}/test` | `llm:write` | Path：`model_id` | 成功 `{ok,elapsed_ms,candidate_answer,answer_text,explanation,confidence}`；失败 `{ok:false,elapsed_ms,error}` |
| `GET` | `/api/v1/llm-runtime-config` | `llm:read` | 无 | `{ok,config}` |
| `PATCH` | `/api/v1/llm-runtime-config` | `llm:write` | JSON：见 `LlmRuntimeConfigPayload` | `{ok,config}` |
| `GET` | `/api/v1/llm-stats` | `llm:read` | 无 | `{ok,stats}` |
| `GET` | `/api/v1/llm-traces` | `llm:read` | Query：`request_id`、`model_id`、`phase`、`limit`（默认 `50`，上限 `200`）、`page`（默认 `1`） | `{ok,traces,total,page,limit}` |

### `LlmModelCreatePayload`

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `name` | `string` | 否 | `""` | 展示名称 |
| `base_url` | `string` | 否 | `""` | 服务端点 |
| `model` | `string` | 否 | `""` | 模型标识 |
| `api_key` | `string` | 否 | `""` | 服务密钥 |
| `role` | `string` | 否 | `backup` | 主备角色 |
| `priority` | `integer` | 否 | `100` | 调度优先级 |
| `stream` | `boolean` | 否 | `true` | 是否流式调用 |
| `max_completion_tokens` | `integer` | 否 | `700` | 最大输出令牌数 |
| `timeout_seconds` | `number` | 否 | `30` | 请求超时秒数 |
| `status` | `string` | 否 | `active` | 配置状态 |

`LlmModelUpdatePayload` 的字段与创建模型相同且全部可选。更新时仅应用非 `None` 字段；空字符串会按请求值写入。

### `LlmRuntimeConfigPayload`

全部字段可选，类型均为 `string`，用于更新运行时配置：

`llm_fallback`、`llm_explain`、`allow_known_rules`、`no_local_bank_mode`、`search_first`、`self_consistency_repeats`、`web_search_provider`、`web_search_configs`、`search_proxy`、`llm_proxy`、`google_search_api_key`、`google_search_cx`、`baidu_search_api_key`、`llm_cache_enabled`、`llm_cache_min_confidence`、`llm_cache_min_confirmations`。
