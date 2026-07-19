# API 契约

更新时间：`2026-07-07`

## 1. 目的

本文件定义当前后端接口的请求、响应和角色边界。接口分为两类：

- 题库查询接口：供 OCS 或其他客户端查题
- 平台管理接口：供用户、管理员、超级管理员管理令牌、积分、日志与反馈

## 2. 鉴权与角色

### 2.1 鉴权方式

- 浏览器控制台：登录后使用会话 Cookie
- OCS 客户端：使用 `Authorization: Bearer <token>`

### 2.2 角色

- `superadmin`
  - 首个注册用户
  - 可调整积分消耗规则
  - 可修改用户角色、状态、积分
  - 可查看所有用户日志与反馈
- `admin`
  - 可查看所有用户日志与反馈
  - 可修改普通用户的状态与积分
  - 不可调整用户等级
  - 不可修改积分计费规则
  - 不可修改系统配置
- `user`
  - 可创建和吊销自己的 API 令牌
  - 只能查看自己的使用日志、自己的反馈和自己的看板

## 3. 题库查询接口

### 3.1 最小请求

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

### 3.2 扩展请求

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
  "page_url": "https://example.com/exam/123",
  "image_urls": [
    "https://example.com/question.png"
  ],
  "image_data_urls": [
    "data:image/png;base64,..."
  ],
  "option_image_urls": {
    "A": "https://example.com/a.png"
  },
  "option_image_data_urls": {
    "A": "data:image/png;base64,..."
  },
  "subject": "math",
  "source_context": "practice_set_a",
  "tags": ["arithmetic", "basic"],
  "locale": "zh-CN",
  "request_id": "demo-001"
}
```

### 3.3 规范化响应结构

```json
{
  "ok": true,
  "request_id": "demo-001",
  "query": {
    "title": "1+2 = ?",
    "type": "single",
    "options": ["A. 1", "B. 2", "C. 3", "D. 4"],
    "image_urls": [],
    "option_image_urls": {}
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

### 3.4 错误响应结构

```json
{
  "ok": false,
  "request_id": "demo-001",
  "query": {
    "title": "以下哪个零件为标准件____。",
    "type": "single",
    "options": [],
    "image_urls": [],
    "option_image_urls": {}
  },
  "error": {
    "code": "INPUT_MISSING_OPTIONS",
    "message": "题目缺少可匹配选项，无法安全作答"
  },
  "debug": {
    "input_flags": "missing_options_for_choice"
  }
}
```

### 3.5 字段规则

请求字段：

- `title`：必填字符串
- `options`：可选字符串数组；如果需要，在导入期间将字符串输入规范化为数组
- `page_url`：可选当前题目所在页面地址；服务端可在需要时用作浏览器上下文抓图的 `Referer`
- `image_capture_status`：可选浏览器侧图片抓取状态，常见值为 `inline_complete`、`inline_partial`、`url_only_fallback`
- `image_capture_failures`：可选浏览器侧未成功转成 `data URL` 的图片数量
- `image_urls`：可选图片 URL 数组；仅作为图片题上下文，不保存原图二进制
- `image_data_urls`：可选图片 `data:image/...;base64,...` 数组；优先用于视觉模型与 OCR，不写入题库或 usage log
- `option_image_urls`：可选选项图片映射，键为 `A-Z`
- `option_image_data_urls`：可选选项图片 `data URL` 映射，键为 `A-Z`
- `type`：必填枚举；初始值应为 `single`（单选）、`multiple`（多选）、`judgement`（判断）、`completion`（填空）、`unknown`（未知）
- `subject`：可选字符串
- `source_context`：可选字符串
- `tags`：可选字符串数组
- `locale`：可选字符串
- `request_id`：可选字符串

响应字段：

- `candidate_answer`：规范化的符号答案，例如 `A`、`A#C`、`true` 或填空字符串
- `answer_text`：供人工审核的渲染答案
- `explanation`：简明的原理解释或检索到的解释
- `confidence`：`0.0` 至 `1.0`
- `resolution_mode`：`exact_match`（精确匹配）、`fuzzy_match`（模糊匹配）、`rag_match`（RAG 匹配）、`external_source`（外部源）、`llm_normalized`（LLM 规范化）、`llm_fallback`（LLM 兜底）、`input_anomaly`（输入异常）
- `review_required`：布尔值
- 选择题无真实选项且本地题库未精确命中时，返回 `INPUT_MISSING_OPTIONS`，不进入 AI 兜底、题库沉淀或 AI 缓存
- 图片题可通过 `image_urls` 进入服务端图片读取链路，服务端会先尝试把图片转换为 `data URL` 再交给多模态模型；若无法读取图片，不会把外链继续透传给模型供应商，而是返回 `IMAGE_UNREADABLE`
- 若增强脚本已上传 `image_data_urls` / `option_image_data_urls`，服务端优先直接把内联图片发送给视觉模型，不再依赖外链图床可访问性
- 若 `image_urls` 存在但 `image_data_url_count = 0`，系统会把该请求视为旧链路 URL-only 降级流量，并在 usage context / debug 中标记 `legacy_url_only`

### 3.6 OCS 兼容说明

- 单选题：`data.answer` 返回 `A/B/C...`
- 多选题：`data.answer` 返回 `A#B#C...`
- 判断题：`data.answer` 返回 `对/错`
- 单空填空：`data.answer` 返回文本答案
- 输入异常：返回 `code=1`、`data.answer=null`，`data.ai.error_code` 包含 `INPUT_MISSING_OPTIONS` 或 `IMAGE_UNREADABLE`
- 官方 OCS 配置只保证传递 `${title}`、`${type}`、`${options}`；图片题完整支持依赖本项目生成或维护的增强导入脚本采集 DOM 图片并上传内联 `base64`，单纯粘贴 OCS 配置只能视为旧兼容链路
- 多空填空：`data.answer` 返回 JSON 数组字符串，例如 `["第一空","第二空"]`

## 4. 平台管理接口

### 4.1 会话与账号

#### `POST /auth/register`

公开注册入口受系统配置 `registration_enabled` 控制；当系统已有用户且注册关闭时返回 `403 REGISTRATION_DISABLED`。空库初始化时仍允许创建第一个 `superadmin`。

注册邮箱策略由 `registration_email_mode` 控制：`optional` 为邮箱可选，`required` 为邮箱必填但不验证，`verified` 为邮箱必填且必须通过验证码校验。`verified` 必须先配置完整 SMTP 服务；旧 `email_verification_enabled` 仍可读取，并派生为兼容状态字段。

注册请求携带有效邀请码时，系统按当前 `invite_reward_mode` 决定邀请人、受邀用户或双方获得 `invite_bonus_points`；该规则只作用于后续注册，不回溯既有邀请关系与积分余额。

请求：

```json
{
  "username": "alice",
  "password": "password123",
  "email": "alice@qq.com",
  "email_code": "123456"
}
```

说明：

- 邮箱验证默认关闭，关闭时 `email` 与 `email_code` 仍按旧逻辑可选。
- 开启邮箱验证后，`email` 与 `email_code` 必填；邮箱域名必须命中 `configs/email-domain-whitelist.json`。
- 验证码只用于注册用途，成功注册后立即消费，不能重复使用。

响应：

```json
{
  "ok": true,
  "user": {
    "user_id": "u_001",
    "username": "alice",
    "role": "user",
    "status": "active",
    "email": "alice@example.com",
    "points": 100
  }
}
```

#### `POST /auth/login`

请求：

```json
{
  "username": "alice",
  "password": "password123",
  "remember": true
}
```

响应：

```json
{
  "ok": true,
  "user": {
    "user_id": "u_001",
    "username": "alice",
    "role": "user",
    "status": "active",
    "points": 100
  },
  "token": "session-token",
  "expires_in": 2592000
}
```

#### `GET /auth/session`

返回当前登录用户信息。

#### `POST /auth/logout`

注销当前会话。

#### `POST /auth/reset-request`

请求重置令牌，令牌会打印到服务端控制台。

#### `POST /auth/reset-confirm`

使用令牌提交新密码。

#### `POST /auth/email-verification-codes`

公开发送注册邮箱验证码。接口只在系统配置 `email_verification_enabled=true` 时可用。

请求：

```json
{
  "email": "alice@qq.com",
  "purpose": "register"
}
```

响应：

```json
{
  "ok": true,
  "message": "验证码已发送，请查看邮箱",
  "cooldown_seconds": 60
}
```

错误码：

- `EMAIL_VERIFICATION_DISABLED`：邮箱验证未开启。
- `EMAIL_DOMAIN_NOT_ALLOWED`：邮箱域名不在白名单中。
- `EMAIL_CODE_RATE_LIMITED`：同邮箱或同 IP 发送过于频繁。
- `EMAIL_SEND_FAILED`：SMTP 发送失败。
- `INVALID_INPUT`：邮箱格式、用途或配置不合法。

#### `GET /site-config`

公开读取站点品牌配置，用于登录页、浏览器标题、favicon 与前端初始化。该接口只返回安全展示字段，不暴露完整系统配置。

响应：

```json
{
  "ok": true,
  "site_title": "AI题库",
  "site_logo_url": ""
}
```

说明：

- `site_title` 为空时后端回退为 `AI题库`。
- `site_logo_url` 为空时前端使用默认图标。
- `site_logo_url` 只支持站内绝对路径、`http://` 或 `https://` 地址。

### 4.2 用户与角色

#### `GET /users/me`

返回当前用户与当前积分计费规则摘要。

`billing` 还包含邀请码奖励展示字段：

- `invite_bonus_points`：每位符合条件用户可获得的积分。
- `invite_reward_mode`：`inviter`（仅邀请人）、`invitee`（仅受邀用户）或 `both`（双方各得）。

#### `GET /users`

- 角色：`admin` / `superadmin`
- 返回所有用户列表

#### `PATCH /users/{username}`

- 角色：`admin` / `superadmin`
- 支持字段：
  - `role`
  - `points`
  - `status`

说明：

- `superadmin` 可调整任意用户的角色、状态、积分
- `admin` 只能管理 `user` 角色用户，且不能修改角色等级

### 4.3 API 令牌

#### `GET /tokens`

返回当前用户自己的 API 令牌列表。

#### `POST /tokens`

请求：

```json
{
  "description": "我的 OCS",
  "reject_low_confidence": false,
  "min_answer_confidence": 0.0
}
```

#### `GET /auth/register-status`

公开读取当前注册入口状态，用于登录页和注册页展示：

```json
{
  "ok": true,
  "registration_enabled": true,
  "config_enabled": true,
  "first_user_allowed": false,
  "email_verification_enabled": false,
  "email_required": false
}
```

说明：

- `reject_low_confidence` 默认为 `false`，保持旧 API Key 行为兼容。
- `min_answer_confidence` 为 `0.0` 时使用系统默认信任线；设置为 `0.8` 等值时，该 API Key 会拒绝低于阈值的 OCS 自动回填。
- 被拒绝的低置信度 OCS 响应返回 `code=1`、`message=低信任度答案未作答`，`data.answer=null`，并在 `data.ai.error_code` 中标记 `LOW_CONFIDENCE_ANSWER`。

响应：

```json
{
  "ok": true,
  "token": "sk_stqb_xxx",
  "token_info": {
    "token_id": "t_001",
    "key_mask": "sk_stqb_xx...abcd",
    "description": "我的 OCS",
    "status": "active",
    "reject_low_confidence": false,
    "min_answer_confidence": 0.0
  },
  "ocs_config": {
    "name": "Local Study Question Bank",
    "url": "http://127.0.0.1:8765/ocs/query",
    "headers": {
      "Authorization": "Bearer sk_stqb_xxx"
    }
  }
}
```

#### `POST /tokens/{token_id}/revoke`

吊销当前用户自己的 API 令牌。

### 4.3.1 题库管理

#### `GET /questions`

- 角色：`admin` / `superadmin`
- 权限：`questions:read`
- 数据源：数据库题库表，而不是当前进程内存索引。
- 查询参数：
  - `question_id`：按题库记录 ID 精确定位，主要用于反馈中心跳转题库编辑。
  - `keyword`：搜索题干、选项、答案、解析、来源、标签和 AI 元数据答案文本。
  - `type`：题型筛选。
  - `source`：来源筛选。
  - `status`：状态筛选，支持 `active`、`trusted`、`low_confidence`、`pending`、`conflict`。
  - `updated_start_date` / `updated_end_date`：按修改日期范围筛选，格式为 `YYYY-MM-DD`，结束日期包含当天。
  - `page` / `limit`：分页。

#### `PATCH /questions/{question_id}`

- 角色：`admin` / `superadmin`
- 权限：`questions:write`
- 用于编辑题干、选项、答案、解析等题库字段。
- 状态为 `active` / `trusted` 的记录会同步进入运行时本地索引；`low_confidence`、`pending`、`conflict` 等记录只在题库管理可见，不自动命中作答。

#### `DELETE /questions/{question_id}`

- 角色：`admin` / `superadmin`
- 权限：`questions:write`
- 采用软删除：数据库记录会标记为 `deleted`，默认题库列表不再显示，当前运行时本地索引会立即移除该题。
- 不物理删除 JSONL 来源文件，也不删除历史使用日志、反馈记录、积分流水或调用追溯。
- 启动同步 JSONL 题库时会跳过已软删除的同 ID 记录，避免删除后的题目重启后重新参与命中。
- 重复删除同一题保持幂等，已删除记录继续返回 `ok: true`。
- 成功响应：

```json
{
  "ok": true,
  "question_id": "xxx",
  "status": "deleted"
}
```

#### `POST /questions/reindex`

- 角色：`admin` / `superadmin`
- 权限：`questions:write`
- 从数据库重新构建当前进程内存索引，只载入 `active` 与 `trusted` 记录。

### 4.4 积分计费

#### `GET /billing`

- 角色：`admin` / `superadmin`
- 返回当前积分规则：
  - `local_hit`
  - `web_search`
  - `llm_fallback`

#### `PATCH /billing`

- 角色：仅 `superadmin`
- 请求：

```json
{
  "local_hit": 1,
  "web_search": 2,
  "llm_fallback": 3
}
```

#### `GET /points-policy`

- 角色：`admin` / `superadmin`
- 权限：`billing:read`
- 返回前端表单需要展示或预填的积分策略：
  - `default_user_points`
  - `invite_bonus_points`
  - `invite_reward_mode`：`inviter`、`invitee` 或 `both`
  - `manual_grant_default_points`
  - `redeem_code_default_points`

### 4.5 系统配置

#### `GET /system-config`

- 角色：仅 `superadmin`
- 返回当前系统配置
- 敏感字段不回明文，只返回 `*_configured` 标志

#### `PATCH /system-config`

- 角色：仅 `superadmin`
- 支持字段：
  - `site_title`
  - `site_logo_url`
  - `default_user_points`
  - `invite_bonus_points`
  - `invite_reward_mode`：`inviter`、`invitee` 或 `both`
  - `manual_grant_default_points`
  - `redeem_code_default_points`
  - `smart_proto_enabled`
  - `custom_proto_header`
   - `answer_retry_times`
   - `registration_enabled`
   - `registration_email_mode`：`optional`、`required` 或 `verified`
   - `email_verification_enabled`
  - `smtp_host`
  - `smtp_port`
  - `smtp_security`
  - `smtp_username`
  - `smtp_password`
  - `smtp_from_email`
  - `smtp_from_name`
  - `email_code_ttl_minutes`
  - `email_code_cooldown_seconds`
  - `email_code_daily_limit`
  - `email_code_ip_hourly_limit`
  - `email_code_max_attempts`

说明：

- `smtp_password` 是敏感配置，`GET /system-config` 不返回明文，只返回 `smtp_password_configured`。
- `PATCH /system-config` 中 `smtp_password=""` 表示保持原密码不变。
- 选择 `registration_email_mode=verified` 时必须先完整配置 SMTP 主机、端口、加密方式、用户名、密码和发件邮箱；`required` 不依赖 SMTP。
- 邮箱域名白名单存储在 `configs/email-domain-whitelist.json`，按文件修改时间轻量缓存，修改后无需重启。
- Docker 部署会把宿主机 `configs` 目录只读挂载到容器 `/app/configs`，因此生产环境应在宿主机仓库目录维护白名单文件。

大模型推理、联网搜索和 LLM 学习缓存配置统一通过 `/llm-runtime-config` 维护，系统配置页不再展示这些字段。

响应包含：

```json
{
  "ok": true,
  "config": {
    "smart_proto_enabled": "true",
    "site_title": "AI题库",
    "site_logo_url": "",
    "custom_proto_header": "http",
    "default_user_points": "100",
    "invite_bonus_points": "0",
    "invite_reward_mode": "both",
    "manual_grant_default_points": "100",
    "redeem_code_default_points": "50",
    "answer_retry_times": "3",
    "registration_enabled": "true",
    "email_verification_enabled": "false",
    "smtp_host": "",
    "smtp_port": "465",
    "smtp_security": "ssl",
    "smtp_username": "",
    "smtp_password_configured": false,
    "smtp_from_email": "",
    "smtp_from_name": "AI题库",
    "email_code_ttl_minutes": "10",
    "email_code_cooldown_seconds": "60",
    "email_code_daily_limit": "5",
    "email_code_ip_hourly_limit": "20",
    "email_code_max_attempts": "5"
  },
  "reload_required": false
}
```

邀请码奖励在受邀用户完成注册时读取当前配置。`invite_bonus_points` 表示每位符合条件用户的积分；`both` 表示邀请人与受邀用户各自获得完整积分值。旧配置未保存 `invite_reward_mode` 时按 `both` 处理。

### 4.6 钱包与积分兑换

#### `GET /wallet/me`

返回当前用户钱包摘要：

- `points`

#### `GET /wallet/orders`

查询参数：

- `username`：管理员 / 超级管理员可用
- `limit`

说明：

- `user` 只能查看自己的订单
- `admin` / `superadmin` 可查看全部订单

#### `POST /wallet/grants`

- 角色：`admin` / `superadmin`
- 用于手动发放积分

请求：

```json
{
  "username": "alice",
  "kind": "points",
  "points": 100
}
```

#### `GET /wallet/redeem-codes`

- 角色：`admin` / `superadmin`
- 查看所有兑换码

#### `POST /wallet/redeem-codes`

- 角色：`admin` / `superadmin`
- 创建积分兑换码

请求：

```json
{
  "kind": "points",
  "points": 50,
  "max_uses": 10,
  "expires_at": 1782892800
}
```

`expires_at` 为可选秒级 Unix 时间戳，`0` 或省略表示永久有效；如果传入时间早于当前时间，请求会返回 `INVALID_INPUT`。

#### `POST /wallet/redeem`

- 角色：登录用户
- 使用兑换码兑换积分

请求：

```json
{
  "code": "rc_xxx"
}
```

### 4.7 使用日志

#### `GET /usage-logs`

查询参数：

- `username`：管理员/超级管理员可用
- `keyword`
- `limit`

说明：

- `user` 只能查看自己的日志
- `admin` / `superadmin` 可查看所有用户日志
- 每条日志包含 `elapsed_ms`，表示服务端查题链路耗时（毫秒），旧历史记录可能为 `0.0`
- 本地题库命中时，每条日志会尽量包含 `question_id`、`source_name`、`source_type`、`source_id`、`source_url`，用于反馈中心定位题库记录。旧历史记录或纯联网来源可能为空。

### 4.8 反馈

#### `POST /feedback`

请求：

```json
{
  "usage_log_id": "log_001",
  "title": "答错了",
  "content": "这题答案不对",
  "image_urls": ["https://example.com/a.png"]
}
```

说明：

- `usage_log_id` 可选；从使用记录提交反馈时应传入该字段。
- 当 `usage_log_id` 属于当前用户时，后端会自动快照题干、题型、当时答案、命中方式、置信度、请求 ID 和题库来源信息。
- 不带 `usage_log_id` 的旧式普通反馈仍然兼容，只是没有题库定位上下文。

#### `GET /feedback`

说明：

- `user` 只能查看自己的反馈
- `admin` / `superadmin` 可查看所有反馈
- 返回会包含可选定位字段：`question_id`、`question_title`、`question_type`、`answer_snapshot`、`resolution_mode`、`confidence`、`request_id`、`source_name`、`source_type`、`source_id`、`source_url`、`context`。
- 管理端优先使用 `question_id` 跳转题库编辑；字段为空时只能按题干关键字降级检索。

### 4.9 用户看板

#### `GET /dashboard/summary`

查询参数：

- `days`：默认 `30`，最大 `365`

返回：

- 时间窗口内的使用量
- 积分消耗
- `resolution_mode` 分布
- 按天聚合的趋势数据 `trend`

### 4.10 工作台聚合

#### `GET /dashboard/workbench`

用途：

- 为工作台首页一次性返回聚合数据

建议返回字段：

- `hero`
- `quick_actions`
- `overview`
- `trend`
- `question_distribution`
- `ranking_preview`
- `notifications_preview`
- `service_status`

说明：

- `overview.avg_response_seconds` 由今日 `usage_logs.elapsed_ms > 0` 的真实样本计算，保留两位小数；没有真实样本时返回 `0.0`

### 4.11 排行统计

#### `GET /dashboard/rankings`

查询参数：

- `days`
- `limit`
- `dimension`

建议默认值：

- `days=1`
- `limit=10`
- `dimension=integration`

### 4.12 消息中心

用户侧统一使用通知中心读取公告和消息。公告仍由公告表管理生命周期，消息仍由通知表保存；通知中心只做聚合展示和按用户维度记录已读状态。

#### `GET /notification-center`

查询参数：

- `status`：可选，`read` / `unread`，为空返回全部。
- `source`：可选，`announcement` / `notification`，为空返回全部来源。
- `limit`：返回数量，默认 `20`，最大 `100`。

返回字段：

- `items`：统一列表项，字段包含 `item_id`、`source`、`level`、`category`、`title`、`content`、`read`、`pinned`、`created_at`、`updated_at`、`expires_at`。
- `unread_count`：当前用户可见公告和消息的未读总数。
- `total`：当前筛选条件下的列表总数。

说明：

- 公告已读按 `announcement_id + updated_at` 判断，公告内容更新后会重新变成未读。
- `user_id=null` 的全局通知在通知中心内按用户回执判断已读，避免一个用户标记已读影响其他用户。

#### `POST /notification-center/{source}/{item_id}/read`

标记通知中心单条内容已读。`source` 只能是 `announcement` 或 `notification`。

#### `POST /notification-center/read-all`

将当前用户可见的公告和消息全部标记为已读。

#### `GET /notifications`

查询参数：

- `status`
- `limit`

#### `POST /notifications/{notification_id}/read`

标记单条消息已读。

#### `POST /notifications/read-all`

全部标记已读。

### 4.13 导入脚本

#### `GET /import-scripts`

返回脚本列表。

#### `POST /import-scripts/generate`

根据 Token 与目标平台生成导入脚本。

请求建议字段：

- `name`
- `token_id`
- `target`
- `include_test_snippet`

#### `GET /import-scripts/{script_id}`

返回脚本详情与内容。

#### `DELETE /import-scripts/{script_id}`

删除脚本记录。

### 4.14 大模型运行配置

#### `GET /llm-runtime-config`

- 角色：`admin`、`superadmin`
- 权限：`llm:read`
- 返回大模型答题、联网搜索和 LLM 学习缓存运行配置。
- `web_search_configs` 返回 JSON 字符串数组；其中单个搜索引擎的 `api_key` 不会返回给前端，只返回 `api_key_configured` 表示是否已保存密钥。

#### `PATCH /llm-runtime-config`

- 角色：仅 `superadmin`
- 权限：`llm:write`
- 支持字段：
  - `llm_fallback`
  - `llm_explain`
  - `allow_known_rules`
  - `no_local_bank_mode`
  - `search_first`
  - `self_consistency_repeats`
  - `web_search_provider`
  - `web_search_configs`
  - `search_proxy`
  - `llm_proxy`
  - `google_search_api_key`
  - `google_search_cx`
  - `baidu_search_api_key`
  - `llm_cache_enabled`
  - `llm_cache_min_confidence`
  - `llm_cache_min_confirmations`
- `web_search_configs` 用于维护联网搜索引擎列表；编辑已有配置时若 `api_key` 留空且 `api_key_configured=true`，后端保留原密钥，运行时内部仍使用未脱敏配置构建搜索 provider。

#### AI 答题沉淀规则

- LLM fallback 只要返回结构化答案内容，就会写入数据库题库表，题库管理可见。
- `confidence >= llm_cache_min_confidence` 且答案通过安全校验时，状态为 `trusted`，可进入本地索引并在后续自动命中。
- 低于信任线的答案状态为 `low_confidence`，题库管理可见，但不进入自动命中索引，下次仍允许继续走 AI 兜底。
- `no_local_bank_mode` 只控制是否读取本地题库，不阻止 AI 答题记录落库。

### 4.15 接入管理

接入管理功能已下线，后端不再注册 `/integrations` 系列接口。导入脚本仍通过 `/import-scripts` 管理，普通用户复制 OCS 接入配置使用 `/tokens/import-script`。复制出的 OCS 题库名称由当前 `site_title` 与 API Key 名称组合生成；API Key 未命名时仅使用掩码末尾四位区分。

### 4.16 兑换管理

管理员通过前端 `/redeem-management` 使用现有钱包接口管理积分兑换码、手动发放积分并查看全平台积分流水。后端不再提供 `/quota-packages` 套餐目录接口。

### 4.17 公告管理

公告是独立资源，不复用消息通知表作为主模型，避免全局通知的已读状态在多用户之间串扰。用户侧只读取当前角色可见且有效的公告，管理侧维护公告生命周期。

#### `GET /announcements`

- 角色：`admin` / `superadmin`
- 权限：`announcements:read`
- 查询参数：
  - `keyword`：按标题或内容搜索。
  - `status`：`draft` / `published` / `archived`。
  - `level`：`info` / `success` / `warning` / `danger`。
  - `audience`：`all` / `user` / `admin` / `superadmin`。
  - `page` / `limit`：分页。
- 返回：`announcements`、`total`、`page`、`limit`。

#### `GET /announcements/active`

- 角色：登录用户
- 返回当前用户角色可见的有效公告。
- 有效条件：`status=published`，且当前时间位于 `starts_at` / `ends_at` 窗口内；`0` 表示不限制。
- 保留兼容旧调用；当前顶栏通知中心通过 `GET /notification-center` 聚合公告，顶部横幅只展示置顶或重要级别的未读公告。

#### `POST /announcements`

- 角色：`admin` / `superadmin`
- 权限：`announcements:write`
- 请求字段：
  - `title`：公告标题，必填。
  - `content`：公告正文，必填，纯文本。
  - `level`：公告等级，默认 `info`。
  - `audience`：投放范围，默认 `all`。
  - `status`：公告状态，默认 `draft`。
  - `pinned`：是否置顶。
  - `starts_at` / `ends_at`：秒级 Unix 时间戳，`0` 表示不限制。

#### `PATCH /announcements/{announcement_id}`

- 角色：`admin` / `superadmin`
- 权限：`announcements:write`
- 支持局部更新公告字段。
- 首次将公告状态改为 `published` 时写入 `published_at`。

#### `DELETE /announcements/{announcement_id}`

- 角色：`admin` / `superadmin`
- 权限：`announcements:write`
- 采用软删除语义：将公告状态改为 `archived`，不物理删除数据库记录。

### 4.17 角色权限

#### `GET /roles`

返回角色列表。

#### `GET /roles/{role_id}/permissions`

返回角色权限矩阵。

#### `PUT /roles/{role_id}/permissions`

更新角色权限矩阵。

## 5. 外部适配器映射说明

该服务应支持一个轻量级的适配器层，其作用是：

- 将传入的占位符或外部字段名称转换为规范化的请求结构
- 将规范化的响应转换为下游消费者所需的格式

请将该适配器保留在核心检索逻辑之外。

## 6. 健康检查端点

推荐端点：

- `GET /api/v1/healthz`
- `GET /version`：公开返回当前镜像的版本、构建提交与构建类型，供部署健康验证使用。
- `GET /status`
- `GET /query?title=...&options=...&type=...`
- `POST /query`
- `GET /ocs/query?title=...&options=...&type=...`
- `POST /ocs/query`

## 7. 版本 1 验证规则

- 拒绝空的 `title`
- 仅在适配器层或导入层将 `options` 字符串强制转换为数组
- 除非明确映射到 `unknown`，否则拒绝不支持的题目类型
- 当 `ok` 为 true 时，始终返回至少一个出处字段
- 当置信度低于阈值或未使用整理过的来源时，将 `review_required` 标记为 true

## 8. 当前本地实现

当前本地实现记录在 [local-service.md](../services/local-service.md) 中。

当前行为：

- 规范化 JSONL 索引
- 精确匹配优先
- 模糊匹配兜底
- 可选的兼容 OpenAI 模型兜底
- 成功响应中必须包含出处信息
- 新增平台用户、令牌、积分、使用日志、反馈与数字看板接口

截图功能与当前接口覆盖差异，详见 [dashboard-interface-coverage.md](dashboard-interface-coverage.md)。
