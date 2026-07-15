# 外部客户端适配器

更新时间：`2026-06-07`

## 1. 目的

本文件描述了外部客户端应如何调用本地学习题库服务。保持外部适配器逻辑尽量薄，以使后端保持可测试性和可重用性。

## 2. 本地端点

默认端点：

```text
http://127.0.0.1:8765/query
```

兼容性端点：

```text
http://127.0.0.1:8765/ocs/query
```

支持的方法：

- `GET`
- `POST`

## 3. 字段映射

外部客户端应将它们的本地字段映射为：

- `title`：题目文本
- `options`：选项数组、换行符分隔的字符串，或 `#` 分隔的字符串
- `type`：题目类型
- `request_id`：可选的追踪 ID

## 4. GET 示例

```text
http://127.0.0.1:8765/query?title=壁胸膜的分部不包括&type=single
```

带选项：

```text
http://127.0.0.1:8765/query?title=...&options=A.xxx#B.xxx#C.xxx#D.xxx&type=single
```

## 5. POST 示例

```json
{
  "title": "壁胸膜的分部不包括",
  "options": ["肋胸膜", "肺胸膜", "膈胸膜", "胸膜顶"],
  "type": "single"
}
```

## 6. 响应处理

外部客户端应使用：

- `ok`
- `result.candidate_answer`
- `result.answer_text`
- `result.explanation`
- `result.confidence`
- `result.review_required`
- `sources`

当 `review_required` 为 true 时，客户端应将答案显示为候选答案以供人工审核。

## 7. OCS 风格源配置结构

对于本地学习和审核场景，后端设计为可轻松被以下结构的源配置调用：

```json
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
  }
}
```

开箱即用的本地配置产物是 [ocs-local-study-bank.json](../configs/ocs-local-study-bank.json)。

服务运行时，它也会在以下地址提供相同的源配置结构：

```text
http://127.0.0.1:8765/api/v1/configs/ocs-local-study-bank.json
```

要为其他主机或端口生成相同的结构：

```powershell
手动修改 [configs/ocs-local-study-bank.json](../configs/ocs-local-study-bank.json) 中的 base URL
```

适配器逻辑应保留 `confidence`、`review_required` 和 `sources`，以便用户可以看到结果的来源。

## 8. 边界

本项目作为本地学习助手构建。客户端集成应展示有来源支持的候选答案以供审核，且不应隐藏低置信度或仅由模型生成的结果。
