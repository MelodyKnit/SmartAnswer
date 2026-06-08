# 模型提供商

更新时间：`2026-06-07`

## 1. 目的

本项目支持一个可选的兼容 OpenAI 的模型提供商。本地检索仍然是第一可信源。仅在启动时明确启用模型层时，才会使用该模型层。

此模型提供商可以指向以下任意一处：

- 暴露了兼容 OpenAI 的 `/chat/completions` 接口的云端 API
- 本地运行时，例如 Ollama、LM Studio 或 vLLM
- 将不同模型提供商规范化在兼容 OpenAI API 之后的自建网关

## 2. 提供商契约

实现文件：

- [providers/base.py](../src/study_qb_assistant/providers/base.py)
- [providers/openai_compatible.py](../src/study_qb_assistant/providers/openai_compatible.py)
- [http_client.py](../src/study_qb_assistant/http_client.py) 包装了 `httpx`，用于处理超时、可选的代理支持、JSON 解码和 HTTP 状态错误。

模型提供商返回：

- `candidate_answer`
- `answer_text`
- `explanation`
- `confidence`

## 3. 环境变量

启用大模型功能时需要配置以下环境变量：

- `STQB_LLM_BASE_URL`：兼容 OpenAI 接口的端点基础 URL
- `STQB_LLM_MODEL`：模型名称

可选变量：

- `STQB_LLM_API_KEY`：API 密钥，仅从环境中读取
- `STQB_LLM_STREAM`：默认为 `true`；对于返回服务器发送事件（Server-Sent Events）流式分块的网关，请保持启用
- `STQB_LLM_MAX_COMPLETION_TOKENS`：默认为 `700`
- `STQB_WEB_SEARCH_PROVIDER`：以逗号分隔的网页搜索提供商；默认为 `duckduckgo`，设为 `none` 以禁用
- `STQB_GOOGLE_SEARCH_API_KEY` 和 `STQB_GOOGLE_SEARCH_CX`：Google 可编程搜索 JSON API 的凭据
- `STQB_BAIDU_SEARCH_API_KEY`：百度千帆 AI 搜索 API 密钥
- `STQB_SEARCH_PROXY`：用于网页搜索请求的可选 HTTP/HTTPS 代理，例如 `http://127.0.0.1:7890`
- `STQB_LLM_PROXY`：用于模型提供商请求的可选 HTTP/HTTPS 代理
- `STQB_AI_CACHE_ENABLED`：默认为 `true`；仅在多次一致后才持久化高置信度的 AI 答案
- `STQB_AI_CACHE_PATH`：可选的 AI 学习库 JSONL 路径；默认为 `data\normalized\ai-learned.jsonl`
- `STQB_AI_CACHE_MIN_CONFIDENCE`：默认为 `0.95`
- `STQB_AI_CACHE_MIN_CONFIRMATIONS`：默认为 `2`
- `STQB_ANSWER_RULES_PATH`：可选的本地规则文件路径；未配置时默认禁用规则文件机制

任何 API 密钥都不应写入项目文件中。

## 4. 启动模式

仅本地检索：

```powershell
.\scripts\run.ps1
```

仅在本地查找未命中时才使用模型：

```powershell
.\scripts\run.ps1
```

使用模型为缺乏解释的本地匹配项添加解释说明：

```powershell
.\scripts\run.ps1
```

同时使用两者：

```powershell
.\scripts\run.ps1
```

## 5. 云端 API 示例

当相比于离线推理，更看重答案质量且本地硬件使用率较低时，请使用此模式。配置的端点必须暴露兼容 OpenAI 的 `/chat/completions` API。

```powershell
$env:STQB_LLM_BASE_URL="https://classbot.top/v1"
$env:STQB_LLM_MODEL="gpt-5.4"
$env:STQB_LLM_API_KEY="your-api-key"
.\scripts\run.ps1
```

请仅在环境变量中保留 API 密钥。不要将其放入 OCS 配置、JSON 文件、示例、日志或源代码中。

ClassBot/New API 风格的网关是通过兼容 OpenAI 的聊天补全（Chat Completions）契约进行处理的。该提供商默认发送 `stream: true`，并在解析答案之前将服务器发送事件（Server-Sent Events）的 `choices[].delta.content` 分块拼接为常规消息内容结构。

设置完环境变量后验证所配置的模型提供商：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8765/status"
```

状态接口不会打印 API 密钥。

## 6. 可选的网页搜索增强

对于模型记忆可能会产生幻觉的问题，服务可以先进行搜索并将网页片段作为证据传递给模型。默认提供商是 DuckDuckGo Instant Answer，它不需要项目 API 密钥。

当前已实现的运行行为：

- 只有在本地检索、直接规则、受信任的 AI 学习库查找以及模糊检索均未命中后，才会进行网页搜索
- 一旦请求进入模型兜底，`SearchAugmentedModelProvider` 会在请求模型前先执行搜索
- 如果搜索返回了证据，该证据将被传入模型提示词中
- 如果搜索未返回证据，或者搜索提供商在近期发生失败后处于冷却期，提供商将退回到纯模型回答
- 当前实现尚未仅因为模型报告的置信度较低而执行第二次网页搜索

默认免密钥模式：

```powershell
$env:STQB_WEB_SEARCH_PROVIDER="duckduckgo"
```

完全禁用网页搜索：

```powershell
$env:STQB_WEB_SEARCH_PROVIDER="none"
```

为搜索引擎使用本地代理：

```powershell
$env:STQB_SEARCH_PROXY="http://127.0.0.1:7890"
```

如果需要，为模型 API 使用代理：

```powershell
$env:STQB_LLM_PROXY="http://127.0.0.1:7890"
```

Google 示例：

```powershell
$env:STQB_WEB_SEARCH_PROVIDER="google"
$env:STQB_GOOGLE_SEARCH_API_KEY="your-google-api-key"
$env:STQB_GOOGLE_SEARCH_CX="your-programmable-search-engine-id"
```

百度示例：

```powershell
$env:STQB_WEB_SEARCH_PROVIDER="baidu"
$env:STQB_BAIDU_SEARCH_API_KEY="your-baidu-ai-search-api-key"
```

可以同时启用两者：

```powershell
$env:STQB_WEB_SEARCH_PROVIDER="google,baidu"
```

搜索密钥仅从环境变量中读取。本项目刻意采用官方 API 形式的提供商，而非爬取搜索结果页面。

## 7. AI 学习题库

服务可以将 AI 生成的答案持久化为常规的题库 JSONL 记录以应对重复的 OCS 请求，但它不会立即信任第一次的模型回答。

默认行为：

- 第一次的高置信度模型答案被存储为 `pending`（待定）状态
- 相同的规范化题目和选项必须至少获得 `2` 次相同的答案
- 只有这样，该 AI 学习库条目才会被晋升为 `trusted`（受信任）状态
- 只有 `trusted` 状态的条目才会被加载到本地检索流中，并标记为 `resolution_mode: ai_cache`
- 产生冲突的模型答案会被标记为 `conflict`（冲突），且不会从学习库中提供

禁用 AI 答案学习功能：

```powershell
$env:STQB_AI_CACHE_ENABLED="false"
```

收紧晋升条件：

```powershell
$env:STQB_AI_CACHE_MIN_CONFIDENCE="0.98"
$env:STQB_AI_CACHE_MIN_CONFIRMATIONS="3"
```

默认的学习库路径为 `data\normalized\ai-learned.jsonl`。每一行都是一条具有 `source_name: AIGenerated`、`ai_generated` 和 `auto_learned` 标签以及 AI 状态元数据的 `CanonicalQuestionRecord` 记录。当启用了基于模型支持的学习路径时，旧的 `data\runtime\ai-answer-cache.json` 条目将被迁移至此 JSONL 格式中。

## 8. 可选规则文件

规则文件机制默认关闭，仅在显式设置环境变量时启用：

```powershell
$env:STQB_ANSWER_RULES_PATH="configs\\my-answer-rules.json"
```

此能力仅适合本地私有场景下的少量固定表达式规则，不应作为常规补题方式，也不建议把运行时规则文件提交进仓库。

## 9. 可靠性规则

- 相比于模型输出，更倾向于采用本地精确或模糊匹配。
- 相比于模型输出，更倾向于采用本地固定表达式规则。
- 受信任的 AI 学习库条目是本地检索的一部分，并带有 `AIGenerated` 来源标签。
- 模型兜底响应被标记为 `resolution_mode: llm_fallback`。
- 模型兜底响应设置 `review_required: true`。
- 即使置信度较低，模型兜底响应仍可返回；低置信度目前影响审核和 AI 库晋升，不影响是否输出 OCS 兼容的答案负载。
- AI 学习库响应被标记为 `resolution_mode: ai_cache`。
- 提供商发生失败时返回结构化的 `MODEL_ERROR` 响应。
- API 密钥仅从环境变量中读取。
- 当配置了网页搜索时，搜索网页片段会被记录以供本地排障，但搜索凭证会被脱敏屏蔽。

## 10. 验证通过的真实提供商

ClassBot/OpenAI 兼容提供商已通过以下配置进行了实测：

- 基础 URL：`https://classbot.top/v1`
- 模型：`gpt-5.4`
- 端点：`/chat/completions`
- 响应模式：流式服务器发送事件（Server-Sent Events）

验证器已通过并将其非敏感结果写入 `data\manifests\configured-model-verification.json` 中。

## 11. 真实本地模型说明

本次会话检查了 `http://127.0.0.1:11434/api/tags`，但该端口上没有运行兼容 Ollama 的服务。

对于 Ollama 风格的兼容 OpenAI 的服务，预期的配置为：

```powershell
$env:STQB_LLM_BASE_URL="http://127.0.0.1:11434/v1"
$env:STQB_LLM_MODEL="qwen2.5:7b"
.\scripts\run.ps1
```

实际模型名称应与本地运行时中安装的模型相匹配。
