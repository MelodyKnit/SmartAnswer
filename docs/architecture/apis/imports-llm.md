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
| `role` | `string` | 否 | `backup` | `primary` 或 `backup`。首个模型自动成为主用；新设主用会将原主用改为备用。兼容旧 `disabled` 请求时停用该模型，角色仍归为主用或备用 |
| `priority` | `integer` | 否 | `100` | 备用顺序，范围 `0`-`9999`，数值越小越先尝试；主用不按此字段排序 |
| `stream` | `boolean` | 否 | `true` | 是否流式调用 |
| `max_completion_tokens` | `integer` | 否 | `700` | 最大输出令牌数 |
| `timeout_seconds` | `number` | 否 | `30` | 请求超时秒数 |
| `status` | `string` | 否 | `active` | 配置状态 |

`LlmModelUpdatePayload` 的字段与创建模型相同且全部可选。更新时仅应用非 `None` 字段；名称、接口地址和模型标识的空白值保留原值，API Key 留空保留原密钥。

修改名称等字段时，不会写回未提交的旧角色、优先级或其他配置；配置界面也只提交实际修改的字段，避免覆盖其他管理员刚完成的主用切换。若编辑期间模型已被删除，返回 HTTP `404` / `MODEL_NOT_FOUND`，不会重新创建该模型。

系统始终保持一个配置为主用（无模型时除外），其余配置均为备用。新设主用与原主用降级在同一事务提交，不会因部分写入失败而丢失原主用。主用优先级只保留为其将来转为备用时的排序值，不参与主用调度。

主用停用或调用失败时，按备用优先级从小到大尝试启用的备用，同优先级时按创建时间、模型 ID 排序。备用调用成功不永久改变角色，下一次请求仍先尝试启用的主用。直接将主用改为备用或删除主用时，自动从其余模型中选择启用且优先级最高者递补；全部停用时仍选出一个配置主用，但不参与调用。只有一个模型时可以停用或删除，但不能改成备用。

启动时会修复旧库中重复主用或无主用的配置：优先保留已有主用中的启用项，按旧优先级、创建时间和模型 ID 确定唯一主用；没有主用时从备用按同样顺序选择。历史 `disabled` 角色转换为备用并设置 `status=inactive`，不会重新启用。此过程不修改表结构。

角色非法或优先级超出 `0`-`9999` 时返回 HTTP `400` / `INVALID_INPUT`；将唯一主用改为备用返回 HTTP `400` / `PRIMARY_MODEL_REQUIRED`。接口路径、响应字段、`llm:read/write` 权限保持不变。

### `LlmRuntimeConfigPayload`

全部字段可选，类型均为 `string`，用于更新运行时配置：

`llm_fallback`、`llm_explain`、`allow_known_rules`、`no_local_bank_mode`、`search_first`、`self_consistency_repeats`、`web_search_provider`、`web_search_configs`、`search_proxy`、`llm_proxy`、`google_search_api_key`、`google_search_cx`、`baidu_search_api_key`、`llm_cache_enabled`、`llm_cache_min_confidence`、`llm_cache_min_confirmations`。
