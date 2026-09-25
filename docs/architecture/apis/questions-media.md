# 题库与媒体 API

标准前缀：`/api/v1`。通用认证、权限、分页和错误格式见[接口约定](conventions.md)。

## 题库

| 方法 | 路径 | 权限 | 请求参数 | 成功响应 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/questions` | `questions:read` | Query：`page`（默认 `1`）、`limit`（默认 `20`）、`keyword`、`question_id`、`type`、`source`、`status`、`updated_start_date`、`updated_end_date` | `{ok,total,page,limit,questions,all_types,all_sources}` |
| `PATCH` | `/api/v1/questions/{question_id}` | `questions:write` | Path：`question_id`；JSON：见下方 `QuestionUpdatePayload` | `{ok,question}` |
| `DELETE` | `/api/v1/questions/{question_id}` | `questions:write` | Path：`question_id` | `{ok,question_id,status:"deleted"}` |
| `POST` | `/api/v1/questions/reindex` | `questions:write` | 无 | `{ok,indexed_count}` |

### `QuestionUpdatePayload`

所有字段可选；未提供的字段保持原值。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `title_raw` | `string` | 题干原文 |
| `question_type` | `string` | 题型 |
| `options_raw` | `array[string]` | 选项原文 |
| `answer_raw` | `string` | 答案原文 |
| `status` | `string` | 题目状态 |
| `answer` | `string` | 结构化答案；当前更新路由接收该字段但不写入题目记录 |
| `answer_text` | `string` | 展示答案；当前更新路由接收该字段但不写入题目记录 |
| `explanation` | `string` | 解析 |
| `subject` | `string` | 学科 |
| `tags` | `array[string]` | 标签 |

## 媒体

媒体内容接口返回二进制流，不使用标准 JSON 成功封装。

| 方法 | 路径 | 权限 | 请求参数 | 成功响应 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/media/ocs/images/{filename}` | 公开 | Path：`filename` | 原始图片二进制；`Content-Type` 按文件类型返回 |
| `GET` | `/api/v1/media/brand/{filename}` | 公开 | Path：`filename` | 品牌媒体二进制；`Content-Type` 按文件类型返回 |
| `GET` | `/api/v1/media/proxy` | 默认公开；启用全局认证时需登录 | Query：`url`，仅允许公共 `http` / `https` URL | 代理目标二进制；`Cache-Control: no-store` |

媒体路径不存在返回 `404`；代理 URL 非法或协议不受支持返回 `400 INVALID_URL`，目标获取失败返回 `404 FETCH_FAILED`。
