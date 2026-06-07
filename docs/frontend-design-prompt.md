# 前端完善设计提示词（StudyQuestionBankAssistant）

> 本文件是分配给实现型 AI 的**任务规格**。AI 应严格按本文件交付，不得偏离技术约束。
> 语言默认：**简体中文**（所有界面文案、占位符、提示、错误信息均为简体中文）。

---

## 0. 角色与目标

你是一名资深前端工程师 + 轻量后端工程师。目标是在现有本地题库检索服务 `StudyQuestionBankAssistant` 上，完善 Web 控制台的**登录/注册/会话体系**，重做一套**全新视觉设计**，打磨现有控制台，并修复前端与后端的字段对接 bug。

交付必须真实可运行，不是仅 UI 外壳：登录/注册要有**真实后端鉴权**（新增 Python 接口 + 用户存储 + token 校验），并保护查询接口。

---

## 1. 项目背景与现状（必须先读）

- 后端：此条为历史前端任务约束，已被当前 FastAPI 迁移目标取代；现行后端 HTTP 层以 `src/study_qb_assistant/api/local_server.py` 的 FastAPI 应用为准，运行时由 uvicorn 提供。
- 前端：单文件 `src/study_qb_assistant/api/static/index.html`（HTML+CSS+原生 JS，无构建步骤），由后端 `/`、`/dashboard` 路由直接读取返回。
- 服务入口：`scripts/serve_local.py`，默认 `127.0.0.1:8765`。
- 现有控制台已有：侧边栏导航、管理员/学生“角色切换”（**仅前端 class 切换，无真实鉴权**）、题库检索测试、API 密钥管理（localStorage 模拟）、推理配置、实时日志。
- 现有 CORS 为 `Access-Control-Allow-Origin: *`。

### 现有 bug（本次必须修复）
现有 `index.html` 的 JS 读取的字段名与后端真实返回**不一致**，导致概览/日志显示不出来：

1. `/status` 真实返回结构（`_status_payload` + `AnswerService.status()`）：
   ```json
   {
     "ok": true,
     "service": "study-question-bank-assistant",
     "lookup": { "provider": "local-normalized-jsonl", "record_count": 123, "source_path": "...", "source_names": [], "source_licenses": [] },
     "model": { "configured": true, "provider": "openai-compatible", "fallback_enabled": true, "explain_local_matches": false, "model": "qwen2.5:7b", "stream": true, "max_completion_tokens": 700, "search_enabled": true, "search_provider": "web-search" },
     "ai_answer_cache": { "enabled": true, "path": "...", "entry_count": 10, "statuses": {"trusted": 3, "pending": 5, "conflict": 2}, "min_confidence": 0.95, "min_confirmations": 2 }
   }
   ```
   - 现有前端错误地读 `data.index_records_loaded`（应为 `data.lookup.record_count`）、`data.llm_fallback_enabled`（应为 `data.model.fallback_enabled`）、`data.llm_model`（应为 `data.model.model`）、`data.llm_base_url`（后端**不返回** base_url，需移除或改用 `data.model.provider`）、`data.web_search_provider`（应为 `data.model.search_provider`）、`data.explain_local_matches`（应为 `data.model.explain_local_matches`）。
   - “待审核数”可用 `data.ai_answer_cache.statuses.pending`；“本地题库量”用 `data.lookup.record_count`。
   - “本地命中率”后端目前**无此字段**，不要再写死 94.2%，要么从 `/debug/recent` 事件里统计 resolution_mode 占比，要么显示“暂无数据”。

2. `/debug/recent` 真实返回：`{ "ok": true, "events": [ { "ts": "2026-06-07T10:14:00+00:00", "event": "query", "title": "...", "answer": "B", "resolution_mode": "exact_match", "confidence": 0.99, "elapsed_ms": 3.2, "path": "/query", ... } ] }`
   - 每个事件是**扁平**结构：时间字段是 `ev.ts`（ISO 字符串，不是 `ev.timestamp` 秒级数字），类型是 `ev.event`（不是 `ev.event_type`），查询详情字段（`title`/`answer`/`resolution_mode`/`elapsed_ms`）直接在事件对象顶层，**不在** `ev.payload` 下。
   - 现有前端读 `ev.timestamp`、`ev.event_type`、`ev.payload.*` 全部错误，必须改对。

3. `/query` 真实返回（`QueryResult.to_api_dict`）：
   ```json
   { "ok": true, "request_id": null,
     "query": { "title": "...", "type": "single", "options": [] },
     "result": { "candidate_answer": "B", "answer_text": "...", "explanation": "...", "confidence": 0.99, "resolution_mode": "exact_match", "review_required": false },
     "sources": [ { "source_name": "CMMLU", "source_type": "qa_record", "source_id": "...", "source_url": "...", "source_license": "...", "score": 0.99 } ],
     "debug": { "retrieval_strategy": "exact_then_fuzzy", "provider": "..." } }
   ```
   - 答案在 `data.result.candidate_answer`，不是 `data.candidate_answer`；失败时为 `{ ok:false, request_id, error:{code,message} }`。题库检索测试页的渲染逻辑要按此结构改对。

---

## 2. 本次交付范围

1. **登录页**（`/login`）：账号 + 密码登录，表单校验、错误提示、加载态、“记住我”，链接到注册与忘记密码。
2. **注册页**（`/register`）：用户名/密码/确认密码（可含可选邮箱），实时校验（密码强度、两次一致、用户名规则），成功后引导回登录。
3. **忘记密码**（最小可用）：本地场景下做“管理员重置/密保问题”或“离线重置令牌”二选一（见 §5.4），UI 要完整，文案说明本地化限制，不要做需要邮件服务器的真实邮件发送。
4. **会话态**：登录后控制台右上显示当前用户名 + 角色 + 退出登录；未登录访问控制台自动跳登录页；token 失效后自动登出并提示。
5. **控制台整体打磨**：套用新设计系统，统一卡片/按钮/表格/弹窗/空状态/响应式（≥1280 桌面优先，兼容到 768），把“角色切换”从假切换改为**读取登录用户的真实角色**。
6. **修复 §1 所有字段对接 bug**。

---

## 3. 全新设计系统（候选基调，三选一并落地）

放弃现有靛蓝 `#4f46e5`+青绿的旧配色，重新设计。从下面三套候选基调中**选一套**并完整落地为 CSS 变量（也可在此基础上微调，但要成体系）：

- **方案 A · 学术墨蓝**：主色 `#1e3a8a`（深墨蓝）/ 强调 `#0ea5e9`（亮天蓝）/ 中性近白 `#f7f8fa` / 文字 `#101828`。沉稳、考试/学术感。
- **方案 B · 清新书院绿**：主色 `#15803d`（书院绿）/ 强调 `#f59e0b`（暖琥珀）/ 米白 `#faf9f6` / 文字 `#1c1917`。温和、护眼、学习氛围。
- **方案 C · 现代石墨紫**：主色 `#6d28d9`（石墨紫）/ 强调 `#06b6d4`（青）/ 冷灰 `#f4f4f7` / 文字 `#18181b`。科技、现代。

设计系统必须包含：
- 完整 CSS 变量（背景/卡片/边框/文字三级/主色+hover/强调/成功-警告-错误 各含底色）。
- 同时提供**浅色为默认**，可加分项：深色模式（`prefers-color-scheme` 或手动切换）。
- 字体延续 `Inter` + `Noto Sans SC`（已通过 Google Fonts 引入），保证中文显示正常；若考虑离线，提供 `system-ui` 回退。
- 圆角、间距、阴影成体系（建议 4/8/12/16/24 间距刻度）。
- 登录/注册页要有独立的、与控制台呼应但更聚焦的版式（建议居中卡片 + 品牌区 + 背景质感，避免和后台一个模子）。
- 可访问性：表单 `label` 关联、focus 可见、对比度达 WCAG AA、错误用文字+颜色双重提示（不只靠颜色）。

---

## 4. 技术约束

- 历史约束中的“后端限用标准库”已不再适用于当前 FastAPI 服务；密码哈希仍使用 `hashlib.pbkdf2_hmac`（加随机 `salt`，迭代≥200000）并禁止明文存储。
- 前端保持**无构建**：纯 HTML+CSS+原生 JS。登录/注册可作为独立 HTML 文件（如 `static/login.html`、`static/register.html`），也可单页内路由切换，自行权衡，但都由后端静态返回。
- 会话 token：推荐用后端签发的随机 token（`secrets.token_urlsafe`）存服务端内存/文件，前端存储优先 `Cookie`（`HttpOnly` 由后端 set-cookie 更安全）；若用 `localStorage` 要在代码注释里写明 XSS 风险。**不要把密码或长期密钥放进 URL 参数**。
- 用户数据持久化：存到 `data/runtime/users.json`（参考现有 `ai_answer_cache.py` 的原子写：先写 `.tmp` 再 `replace`，加 `threading.Lock`）。**不要把该文件提交进 git**，在 `.gitignore` 里排除（若无则新建）。
- 安全收尾：现有 CORS `*` 在带鉴权后是风险，登录态接口应收紧为同源或 `127.0.0.1`；不要在日志里打印密码/token（`runtime_log.py` 已有脱敏，扩展其敏感词即可）。
- 不破坏现有逻辑：`AnswerService` / `LocalQuestionIndex` / `to_ocs_response` / OCS 配置生成等不得改坏；OCS 查询接口 `/ocs/query` 给浏览器脚本用，**鉴权方式要可配置**（见 §5.3），默认不要让现有无 token 的 OCS 客户端直接全挂。

---

## 5. 后端鉴权契约（需新增实现）

在 `local_server.py`（或新建 `src/study_qb_assistant/auth/` 模块，推荐后者，保持分层）实现以下接口。所有响应 `Content-Type: application/json; charset=utf-8`。

### 5.1 注册 `POST /auth/register`
- 入参：`{ "username": "...", "password": "...", "email": "..."(可选) }`
- 规则：用户名 3–32 位、唯一；密码≥8 位。首个注册用户自动成为 `admin`，其余默认 `user`（可在文档中说明）。
- 成功：`{ "ok": true, "user": { "username": "...", "role": "user" } }`
- 失败：`{ "ok": false, "error": { "code": "USERNAME_TAKEN"|"WEAK_PASSWORD"|"INVALID_INPUT", "message": "中文说明" } }`，HTTP 400/409。

### 5.2 登录 `POST /auth/login`
- 入参：`{ "username", "password", "remember": true|false }`
- 成功：签发 token，`Set-Cookie: stqb_session=<token>; HttpOnly; SameSite=Strict; Path=/`（remember 时加 `Max-Age`），返回 `{ "ok": true, "user": { "username", "role" } }`。
- 失败：`{ "ok": false, "error": { "code": "BAD_CREDENTIALS", "message": "用户名或密码错误" } }`，HTTP 401。要做基本的失败计数/节流（防暴力破解，可简单 IP+用户名计数）。

### 5.3 会话 `GET /auth/session` / 退出 `POST /auth/logout`
- `/auth/session`：读 Cookie 校验 token，有效返回 `{ "ok": true, "user": {...} }`，无效 `{ "ok": false }`(401)。
- `/auth/logout`：清除服务端 token 并过期 Cookie，返回 `{ "ok": true }`。
- 受保护接口：`/query`、`/ocs/query`、`/status`、`/debug/recent`、写操作等，未登录返回 401。
  - **OCS 兼容性**：`/ocs/query` 给浏览器脚本用，要支持 `Authorization: Bearer <api_key>` 头（沿用现有 API 密钥体系思路）或可通过环境变量 `STQB_REQUIRE_AUTH`（默认值你来定，建议默认 `false` 以不破坏现状，登录态 UI 单独走 Cookie）开关。把这个取舍在文档/注释里讲清楚。

### 5.4 忘记密码（本地化，二选一并实现其一）
- **方案甲（推荐，离线重置令牌）**：`POST /auth/reset-request` 生成一次性重置令牌并**打印到服务器控制台/日志**（本地单机场景，无邮件服务器），用户从控制台复制；`POST /auth/reset-confirm` 用 `{ token, new_password }` 重置。
- **方案乙（密保问题）**：注册时设密保问答，重置时校验。
- UI 要完整呈现所选方案的步骤与中文说明。

---

## 6. 验收标准

1. 全新跑通：删除 `data/runtime/users.json` 后，访问控制台被重定向到登录页；注册首个用户成为管理员；登录后进入控制台，右上显示用户名+角色+退出。
2. 未登录直接打开控制台或调 `/status` 返回 401 并跳登录（按 §5.3 配置）。
3. 退出后 token 失效，再访问受保护页要求重新登录。
4. 概览页四个指标卡显示真实数据（题库量、LLM 状态、resolution_mode 占比或“暂无数据”、待审核 pending 数），日志页能正确按 `ev.ts`/`ev.event` 渲染，题库检索测试按 `data.result.*` 渲染——即 §1 三个 bug 全部修复。
5. 登录/注册/忘记密码三页表单校验、错误提示、加载态、空状态完整，全中文。
6. 新设计系统在登录页与控制台一致落地；响应式在 1280 与 768 两个断点正常。
7. 历史前端任务约束中的“后端无新增第三方依赖”已被当前 FastAPI/httpx 服务目标取代；密码非明文；`users.json` 已在 `.gitignore`。
8. `python -m unittest discover -s tests` 现有测试不被破坏；为新增鉴权逻辑补充至少覆盖“注册→登录→校验 token→登出”和“错误密码被拒”的单元测试。

---

## 7. 交付物清单

- 新/改前端：`static/login.html`、`static/register.html`（或单页路由）、改造后的 `static/index.html`。
- 新后端：鉴权模块（建议 `src/study_qb_assistant/auth/`：用户存储 + 密码哈希 + token 管理）、`local_server.py` 路由与守卫接入。
- `.gitignore` 排除 `data/runtime/users.json`。
- 新增鉴权单元测试（`tests/test_auth.py`）。
- 简短改动说明：新增接口、环境变量开关、如何本地跑通登录流程。

---

## 8. 实现注意

- 先读这些文件再动手：`src/study_qb_assistant/api/local_server.py`、`src/study_qb_assistant/api/static/index.html`、`src/study_qb_assistant/runtime_log.py`、`src/study_qb_assistant/ai_answer_cache.py`（参考原子写/Lock 风格）、`scripts/serve_local.py`、`src/study_qb_assistant/answering.py` 的 `status()`。
- 小步改、可回滚；不要顺手重构无关代码。
- 任何破坏性或高风险操作（删库、改安全控制）前先停下说明。
