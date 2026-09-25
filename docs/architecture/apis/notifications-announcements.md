# 通知与公告 API

标准前缀：`/api/v1`。通知读取接口要求登录；公告管理接口使用显式权限控制。

## 通知

| 方法 | 路径 | 权限 | 请求参数 | 成功响应 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/notifications` | 登录 | Query：`status`、`limit`（默认 `20`） | `{ok,notifications}` |
| `GET` | `/api/v1/notification-center` | 登录 | Query：`status`、`source`、`limit`（默认 `20`，上限 `100`） | `{ok,items,unread_count,total}` |
| `POST` | `/api/v1/notification-center/{source}/{item_id}/read` | 登录 | Path：`source`、`item_id` | `{ok,item}` |
| `POST` | `/api/v1/notification-center/read-all` | 登录 | 无 | `{ok,count}` |
| `POST` | `/api/v1/notifications/{notification_id}/read` | 登录 | Path：`notification_id` | `{ok,notification}` |
| `POST` | `/api/v1/notifications/read-all` | 登录 | 无 | `{ok,count}` |

## 公告

| 方法 | 路径 | 权限 | 请求参数 | 成功响应 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/announcements` | `announcements:read` | Query：`keyword`、`status`、`level`、`audience`、`page`（默认 `1`）、`limit`（默认 `20`，上限 `100`） | `{ok,total,page,limit,announcements,audience_options}` |
| `GET` | `/api/v1/announcements/active` | 登录 | Query：`limit`（默认 `10`） | `{ok,announcements}` |
| `POST` | `/api/v1/announcements` | `announcements:write` | JSON：见 `AnnouncementCreatePayload` | `{ok,announcement}` |
| `PATCH` | `/api/v1/announcements/{announcement_id}` | `announcements:write` | Path：`announcement_id`；JSON：更新字段 | `{ok,announcement}` |
| `DELETE` | `/api/v1/announcements/{announcement_id}` | `announcements:write` | Path：`announcement_id` | `{ok,announcement_id,status}` |

### `AnnouncementCreatePayload`

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `title` | `string` | 否 | `""` | 标题 |
| `content` | `string` | 否 | `""` | 内容 |
| `level` | `string` | 否 | `info` | 公告级别 |
| `audience` | `string` | 否 | `all` | 目标受众 |
| `status` | `string` | 否 | `draft` | 发布状态 |
| `pinned` | `boolean` | 否 | `false` | 是否置顶 |
| `starts_at` | `number` | 否 | `0` | 生效时间戳 |
| `ends_at` | `number` | 否 | `0` | 失效时间戳 |

`PATCH` 支持上述字段的可选子集；时间戳为 `0` 时按服务端约定处理。

`title` 和 `content` 在请求模型中默认为空字符串，但公告服务的业务校验要求两者非空。
