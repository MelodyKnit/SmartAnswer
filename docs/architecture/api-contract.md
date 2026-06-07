# API 契约

更新时间：`2026-06-07`

## 1. 目的

本文件定义了学习助手服务的规范化内部 API。该设计特意与客户端解耦，以便即使后续下游工具或适配器发生变化，后端也能保持稳定。

## 2. 请求结构

### 2.1 最小请求

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

### 2.2 扩展请求

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

## 3. 规范化响应结构

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

## 4. 错误响应结构

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

## 5. 字段规则

### 请求字段

- `title`：必填字符串
- `options`：可选字符串数组；如果需要，在导入期间将字符串输入规范化为数组
- `type`：必填枚举；初始值应为 `single`（单选）、`multiple`（多选）、`judgement`（判断）、`completion`（填空）、`unknown`（未知）
- `subject`：可选字符串
- `source_context`：可选字符串
- `tags`：可选字符串数组
- `locale`：可选字符串
- `request_id`：可选字符串

### 响应字段

- `candidate_answer`：规范化的符号答案，例如 `A`、`A#C`、`true` 或填空字符串
- `answer_text`：供人工审核的渲染答案
- `explanation`：简明的原理解释或检索到的解释
- `confidence`：`0.0` 至 `1.0`
- `resolution_mode`：`exact_match`（精确匹配）、`fuzzy_match`（模糊匹配）、`rag_match`（RAG 匹配）、`external_source`（外部源）、`llm_normalized`（LLM 规范化）、`fallback`（兜底）
- `review_required`：布尔值

## 6. 外部适配器映射说明

该服务应支持一个轻量级的适配器层，其作用是：

- 将传入的占位符或外部字段名称转换为规范化的请求结构
- 将规范化的响应转换为下游消费者所需的格式

请将该适配器保留在核心检索逻辑之外。

## 7. 健康检查端点

推荐端点：

- `GET /healthz`
- `GET /readyz`
- `GET /providers`
- `GET /query?title=...&options=...&type=...`
- `POST /query`
- `GET /ocs/query?title=...&options=...&type=...`
- `POST /ocs/query`

建议的 `GET /providers` 响应：

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

## 8. 版本 1 验证规则

- 拒绝空的 `title`
- 仅在适配器层或导入层将 `options` 字符串强制转换为数组
- 除非明确映射到 `unknown`，否则拒绝不支持的题目类型
- 当 `ok` 为 true 时，始终返回至少一个出处字段
- 当置信度低于阈值或未使用整理过的来源时，将 `review_required` 标记为 true

## 9. 当前本地实现

当前本地实现记录在 [local-service.md](../services/local-service.md) 中。

当前行为：

- 规范化 JSONL 索引
- 精确匹配优先
- 模糊匹配兜底
- 可选的兼容 OpenAI 模型兜底
- 成功响应中必须包含出处信息
- 默认不需要外部模型提供商
