# OCS 使用手册

更新日期：`2026-06-07`

## 1. 当前交付目标

本项目已经整理成“本地题库服务 + 可切换大模型提供商（Provider） + OCS 风格配置”的结构。

核心链路：

```text
OCS 配置
  -> http://127.0.0.1:8765/ocs/query
  -> 本地题库优先检索
  -> 本地未命中时进入固定规则、AI 已信任题库、模糊检索
  -> 仍未命中时可选调用 OpenAI 兼容大模型 API
  -> 返回 answer、answer_text、explanation、ai 元数据
```

当前实际工作流基线：

```text
本地精确匹配
  -> 固定高信号规则
  -> AI 已信任题库
  -> 本地模糊匹配
  -> 模型兜底
     -> 若启用联网搜索，则先搜索再问模型
     -> 搜到证据则带证据作答
     -> 没搜到证据则直接模型作答
```

这里特别说明一下：现在还不是“模型先答，如果不确定再回头联网搜索”的实现，而是“进入模型兜底链路后，先尝试联网搜索”。这份文档记录的是当前已实现行为，后续如果我们切换到更严格的“不确定再强制搜索”策略，再单独作为流程变更记录。

模型不绑定 Ollama。只要服务端配置的是 OpenAI 兼容的 `/chat/completions` 接口，可以接本地 Ollama、LM Studio、vLLM，也可以接 DeepSeek、通义千问、智谱、OpenAI 兼容的网关等云 API。

## 2. Conda 环境

环境名已经按要求使用 `ai` 开头：

```powershell
conda env create -f environment.yml
conda activate ai-study-qb
```

如果环境已经存在：

```powershell
conda activate ai-study-qb
```

## 3. 启动本地服务

只使用本地题库：

```powershell
.\scripts\run.ps1
```

使用更大的已验证索引：

```powershell
.\scripts\run.ps1
```

开发模式热重载：

```powershell
.\scripts\run-dev.ps1
```

## 4. 接入云 API 大模型

不要把 API 密钥（API Key）写进 OCS 配置。推荐放在本地服务环境变量里。

通用 OpenAI 兼容配置：

```powershell
$env:STQB_LLM_BASE_URL="https://api.example.com/v1"
$env:STQB_LLM_MODEL="your-model-name"
$env:STQB_LLM_API_KEY="your-api-key"
.\scripts\run.ps1
```

说明：

- `--llm-fallback` 表示本地题库查不到时再问模型。
- `--llm-explain` 表示本地命中但缺少解析时让模型补解析。
- 模型兜底结果会带 `review_required: true`，避免把模型猜测伪装成题库命中。
- 当前即使模型置信度较低，也可能仍返回给 OCS，但不会直接晋升为可信 AI 题库；低置信度主要影响审核标记和是否允许沉淀。
- ClassBot/New API 这类网关按 OpenAI 兼容的 Chat Completions 接入；本项目默认使用流式响应并解析 `choices[].delta.content`。
- 单选题会返回 `A`、`B` 等字母；多选题会返回 OCS 更容易识别的 `A#B#C` 格式。

默认联网搜索增强不需要密钥（key），使用 DuckDuckGo 即时回答（DuckDuckGo Instant Answer）：

```powershell
$env:STQB_WEB_SEARCH_PROVIDER="duckduckgo"
```

如果完全不想联网搜索：

```powershell
$env:STQB_WEB_SEARCH_PROVIDER="none"
```

如果 Google/DuckDuckGo 等搜索访问不稳定，可以给搜索单独配置代理：

```powershell
$env:STQB_SEARCH_PROXY="http://127.0.0.1:7890"
```

如果大模型 API 也需要代理，可以单独配置：

```powershell
$env:STQB_LLM_PROXY="http://127.0.0.1:7890"
```

可选付费/高命中率搜索 API：

```powershell
$env:STQB_WEB_SEARCH_PROVIDER="google,baidu"
$env:STQB_GOOGLE_SEARCH_API_KEY="your-google-api-key"
$env:STQB_GOOGLE_SEARCH_CX="your-programmable-search-engine-id"
$env:STQB_BAIDU_SEARCH_API_KEY="your-baidu-ai-search-api-key"
```

搜索增强默认使用 `duckduckgo`，不需要密钥（key）；如果网络不稳定或不想联网，可设置 `STQB_WEB_SEARCH_PROVIDER="none"`。本地题库仍然优先；本地没命中时先调用搜索 API 获取证据片段，再把证据和题目一起交给大模型作答，用于降低模型凭记忆幻觉。搜索失败会进入短期冷却，避免每道题都卡在同一个不可达搜索源上。

LLM 自动沉淀题库默认开启，但不会把模型第一次回答直接当题库复用：

```powershell
$env:STQB_LLM_CACHE_ENABLED="true"
$env:STQB_LLM_CACHE_MIN_CONFIDENCE="0.95"
$env:STQB_LLM_CACHE_MIN_CONFIRMATIONS="2"
```

AI 学习结果默认写入 `data\normalized\ai-learned.jsonl`，格式与普通题库一致，来源标为 `AIGenerated`，并带有 `ai_generated`、`auto_learned`、`status:*` 等标签。第一次高置信模型答案会先记为 `pending`（待处理），同题同选项后续再次得到相同答案才晋升为 `trusted`（已信任）；只有 `trusted` 才会进入本地检索并以 `resolution_mode: ai_cache` 返回。若模型对同一题给出冲突答案，该条记录会进入 `conflict`（冲突），不会被用于自动答题。旧版 `data\runtime\ai-answer-cache.json` 会在启用模型学习时作为兼容来源迁移。

如果你确实需要本地私有规则文件，可以显式设置：

```powershell
$env:STQB_ANSWER_RULES_PATH="configs\\my-answer-rules.json"
```

默认不启用规则文件机制，也不建议把运行时规则文件提交到仓库。

## 5. 接入本地模型

Ollama 只是可选方案，不是项目依赖。

如果使用 Ollama 的 OpenAI 兼容接口：

```powershell
$env:STQB_LLM_BASE_URL="http://127.0.0.1:11434/v1"
$env:STQB_LLM_MODEL="qwen2.5:7b"
.\scripts\run.ps1
```

如果使用 LM Studio、vLLM 或其他本地服务，把 `STQB_LLM_BASE_URL` and `STQB_LLM_MODEL` 改成对应服务即可。

## 6. OCS 配置

本地服务运行后，可以直接使用这个配置：

```json
[
  {
    "name": "Local Study Question Bank",
    "homepage": "http://127.0.0.1:8765/api/v1/healthz",
    "url": "http://127.0.0.1:8765/ocs/query",
    "method": "get",
    "type": "GM_xmlhttpRequest",
    "contentType": "json",
    "data": {
      "title": "${title}",
      "options": "${options}",
      "type": "${type}"
    },
    "handler": "return (res)=>res.code === 0 ? [res.data.question, res.data.answer] : [res.message || (res.data && res.data.question) || '未找到答案', undefined]"
  }
]
```

注意：OCS 的 handler 返回值第二项才是答案，所以成功时返回 `[question, answer]`。

同一份配置也在项目文件中：

```text
configs\ocs-local-study-bank.json
```

服务启动后也可以从接口获取：

```text
http://127.0.0.1:8765/api/v1/configs/ocs-local-study-bank.json
```

如果 OCS/Tampermonkey 拦截跨域请求，请在脚本或管理器配置中允许连接：

```text
127.0.0.1
localhost
```

## 7. 自测命令

健康检查：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/v1/healthz"
```

确认题库和模型开关状态：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8765/status"
```

题库查询：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8765/ocs/query?title=壁胸膜的分部不包括&type=single"
```

模拟“读取配置、替换占位符、请求题库、执行 handler”的完整客户端流程：

```powershell
在 OCS/Tampermonkey 中直接加载配置并发起一次真实查询
```

检查当前已经运行在 `8765` 的真实服务：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8765/status"
```

设置模型环境变量后，验证真实模型提供商（Provider）：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8765/status"
```

如果题库没有命中但希望继续由大模型回答，启动服务时必须启用模型兜底：

```powershell
.\scripts\run.ps1
```

完整验收：

```powershell
python -m pytest tests -q
```

## 8. 当前题库状态

已本地整理的索引：

- `data\normalized\cmmlu.jsonl`：`11917` 条。
- `data\normalized\agieval-mcq.jsonl`：`6154` 条。
- `data\normalized\verified.jsonl`：`18071` 条。

使用建议：

- 初次验证用 `cmmlu.jsonl`，速度快且已覆盖基础链路。
- 想扩大命中范围用 `verified.jsonl`。
- M3KE 已下载但许可证仍需人工确认，不默认加入 `verified.jsonl`。
- C-Eval 仓库资料已下载，但完整数据包在当前网络环境未成功拉取。

## 9. 可靠性边界

项目默认不接入未知来源的免费搜题接口，也不默认爬取第三方网站。原因是这些来源通常缺少公开协议、稳定性证明、授权边界和可审计来源。

后续如果找到明确授权、公开契约、稳定可验证的题库 API，可以按“外部源适配器（External source adapter）”的方式接入，不影响现有 OCS 配置。
