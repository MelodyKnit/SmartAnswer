# 用量、反馈与工作台 API

标准前缀：`/api/v1`。分页参数默认值和认证格式见[接口约定](conventions.md)。

## 用量日志

| 方法 | 路径 | 权限 | 请求参数 | 成功响应 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/usage-logs` | 登录；普通用户仅可查看自身记录 | Query：`username`、`token_id`、`api_key_id`、`log_id`、`keyword`、`start_date`、`end_date`、`limit`（默认 `100`，上限 `500`）、`page`（默认 `1`） | `{ok,logs,total,page,limit}` |

具有 `dashboard:all` 权限的用户可跨用户查询；普通用户传入其他用户筛选条件时按权限限制处理。日期格式错误返回 `400 INVALID_DATE`。

## 反馈

| 方法 | 路径 | 权限 | 请求参数 | 成功响应 |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/feedback` | `feedback:self` | JSON：见 `FeedbackPayload` | `{ok,feedback}` |
| `GET` | `/api/v1/feedback/answer-records` | `feedback:self` | Query：`keyword`、`days`（默认 `1`）、`deduplicate`（默认 `false`）、`question_id`、`limit`（默认 `50`，上限 `100`）、`page`（默认 `1`） | `{ok,records,groups,total,page,limit,deduplicated}`；`deduplicate=false` 时使用 `records`，否则使用 `groups` |
| `GET` | `/api/v1/feedback` | 登录；跨用户需 `feedback:manage` | Query：`username`、`status`、`category`、`limit`（默认 `100`，上限 `500`）、`page`（默认 `1`） | `{ok,feedbacks,total,page,limit}` |
| `PATCH` | `/api/v1/feedback/{feedback_id}` | `feedback:manage` | Path：`feedback_id`；JSON：见 `FeedbackResolvePayload` | `{ok,feedback,granted_points}` |

### `FeedbackPayload`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `usage_log_id` | `string` | 否 | 关联单条用量记录 |
| `usage_log_ids` | `array[string]` | 否 | 关联多条用量记录 |
| `title` | `string` | 否 | 反馈标题 |
| `content` | `string` | 否 | 反馈内容 |
| `image_urls` | `array[string]` | 否 | 反馈图片地址 |
| `category` | `string` | 否 | 反馈分类，默认 `answer` |

### `FeedbackResolvePayload`

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `status` | `string` | `resolved` | 处理状态 |
| `admin_note` | `string` | `""` | 管理员备注 |
| `corrected_answer` | `string` | `""` | 修正答案 |
| `reward_points` | `integer` | `0` | 奖励积分 |

## 工作台

以下接口要求登录。`scope` 用于选择可见范围，跨用户范围由权限控制。

| 方法 | 路径 | 认证/权限 | 请求参数 | 成功响应 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/dashboard/workbench` | 登录；无 `dashboard:all` 时全局范围降级为个人范围 | Query：`scope` | `{ok,workbench}` |
| `GET` | `/api/v1/dashboard/rankings` | 登录；无 `dashboard:all` 时全局范围降级为个人范围 | Query：`days`（默认 `1`）、`limit`（默认 `10`，服务端上限 `50`）、`dimension`（默认 `provider`）、`scope` | `{ok,rankings}` |
| `GET` | `/api/v1/dashboard/summary` | 登录；无 `dashboard:all` 时全局范围降级为个人范围 | Query：`days`（默认 `30`，服务端上限 `365`）、`scope` | `{ok,summary}` |
