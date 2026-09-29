# 钱包与计费 API

标准前缀：`/api/v1`。积分、配额和套餐相关操作均受服务端权限与业务校验约束。通用错误格式见[接口约定](conventions.md)。

## 钱包与订单

| 方法 | 路径 | 权限 | 请求参数 | 成功响应 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/wallet/me` | 登录 | 无 | `{ok,wallet}` |
| `GET` | `/api/v1/wallet/orders` | 登录 | Query：`source`、`limit`（默认 `100`）、`page`（默认 `1`） | `{ok,orders,total,page,limit}` |
| `GET` | `/api/v1/wallet/changes` | `wallet:changes:read` | Query：`username`、`kind`、`source`、`limit`（默认 `100`）、`page`（默认 `1`） | `{ok,orders,total,page,limit}` |
| `POST` | `/api/v1/wallet/grants` | `wallet:changes:write` | JSON：见 `WalletGrantPayload` | `{ok,order}` |
| `POST` | `/api/v1/wallet/redeem` | 登录 | JSON：`{code}` | `{ok,order,wallet,user}` |

### `WalletGrantPayload`

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `username` | `string` | 否 | `""` | 目标用户；模型可省略，业务校验要求有效用户 |
| `kind` | `string` | 否 | `points` | 变更类型 |
| `points` | `integer` | 否 | `0` | 积分数量 |
| `days` | `integer` | 否 | `0` | 有效期天数 |

## 兑换码

| 方法 | 路径 | 权限 | 请求参数 | 成功响应 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/wallet/redeem-codes` | `wallet:changes:write` | Query：`page?`、`limit?` | 传分页参数时返回 `{ok,redeem_codes,total,page,limit,summary}`；不传时兼容旧行为，返回完整 `redeem_codes` 列表 |
| `POST` | `/api/v1/wallet/redeem-codes` | `wallet:changes:write` | JSON：见 `RedeemCodePayload` | `{ok,redeem_code}` |
| `DELETE` | `/api/v1/wallet/redeem-codes/{code_id}` | `wallet:changes:write` | Path：`code_id` | `{ok,message}` |
| `POST` | `/api/v1/wallet/redeem-codes/batch-delete` | `wallet:changes:write` | JSON：`{code_ids: string[]}` | `{ok,deleted_count}` |

### `RedeemCodePayload`

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `title` | `string` | 否 | `""` | 管理端备注标题，可重复；首尾空白会被移除，最多 255 字符 |
| `kind` | `string` | 否 | `points` | 兑换内容类型 |
| `points` | `integer` | 否 | `0` | 积分数量 |
| `days` | `integer` | 否 | `0` | 有效期天数 |
| `max_uses` | `integer` | 否 | `1` | 最大兑换次数 |
| `expires_at` | `number` | 否 | `0` | 过期时间戳；`0` 表示不设置 |
| `code` | `string` | 否 | 自动生成 | 指定兑换码 |
| `count` | `integer` | 否 | `1` | 批量生成数量 |

标题仅用于兑换码管理列表识别，不参与兑换码唯一性校验，也不改变兑换流程。随机批量创建时，该批所有兑换码共用请求中的标题。

兑换码管理列表支持服务端分页：`page` 最小值为 `1`，`limit` 范围为 `1-100`，只传一个参数时另一项默认 `1/20`。分页响应中的 `summary` 始终基于全量兑换码统计，字段为 `total_codes`、`usable_codes`、`exhausted_codes`、`used_uses` 和 `max_uses`，不随当前页变化。为兼容旧调用方，不带分页参数时仍返回全量列表及原响应结构。

## 计费策略

| 方法 | 路径 | 权限 | 请求参数 | 成功响应 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/points-policy` | `billing:read` | 无 | `{ok,points_policy}` |
| `GET` | `/api/v1/billing` | `billing:read` | 无 | `{ok,billing}` |
| `PATCH` | `/api/v1/billing` | `billing:write` | JSON：见 `BillingPayload` | `{ok,billing}` |

### `BillingPayload`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `local_hit` | `integer \| null` | 否 | 本地命中计费配置 |
| `web_search` | `integer \| null` | 否 | 网络检索计费配置 |
| `llm_fallback` | `integer \| null` | 否 | LLM 回退计费配置 |

字段值由当前计费配置模型校验；未提供字段保持原配置。
