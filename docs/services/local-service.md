# 本地服务

更新时间：`2026-06-07`

## 1. 目的

本地服务在规范化的 JSONL 数据之上暴露出一个简易的、面向学习的题目检索 API。它返回带有出处和置信度元数据的候选答案。

HTTP 层使用 FastAPI 实现并由 uvicorn 运行。业务逻辑保留在检索 (retrieval)、解答 (answering)、模型提供商 (provider) 和身份验证 (auth) 模块中，以保持路由处理足够轻量。运行时状态默认使用 SQLAlchemy + SQLite 持久化；若配置 Redis，则会话和最近事件优先进入 Redis。大模型提供商是可选的，并且默认禁用。

当前运行时索引装载策略：

- 启动时仍会读取 `data/normalized/verified.jsonl` 与 `data/normalized/ai-learned.jsonl` 作为种子来源
- 种子来源会先同步进数据库题库表
- 当应用接入真实平台/鉴权服务时，运行时内存索引会再从数据库中的“可自动命中记录”重建
- 因此，人工评审题、数据库修订题和可信 AI 题可以在不改动基础 JSONL 的情况下参与后续命中

## 2. 当前已实现的答案工作流

当前运行时的工作流特意被记录为今天已存在的行为，而非未来的理想流程。

```text
OCS 或 `/api/v1/query` 请求（`/query` 仅为兼容别名）
  -> 本地精确匹配
  -> 直接固定答案规则
  -> 受信任的 AI 学习库匹配
  -> 本地模糊匹配
  -> 模型兜底
     -> 若配置了网页搜索，先进行搜索
     -> 若搜索返回了证据，将证据传递给模型
     -> 若搜索未返回证据，在无证据的情况下调用模型
  -> 返回带有出处和审核标记的答案
```

当前注意事项：

- 本地检索仍然是第一可信源
- 受信任的 AI 学习库条目其行为类似于本地题库记录，并在模糊兜底匹配完成前进行检索
- 网页搜索目前是模型兜底路径的一部分，而不是在模型声明不确定之后才运行的第二阶段重试
- 模型兜底答案返回时将带有 `resolution_mode: llm_fallback` 和 `review_required: true`
- 低置信度的模型答案不会晋升到 AI 学习库，除非它们满足所配置的确认阈值
- 当前实现仍可向 OCS 返回低置信度的兜底答案；审核边界携带在 `data.ai` 中

当前记录的工作流是项目目前遵循的基线行为。如果后续策略变更为“本地 -> 模型 -> 不确定 -> 强制搜索重试”，这应该被记录为刻意的行为变更，而不是假设其已经存在。

## 3. 导出规范化索引

当前已验证结果：

- 输出：`data\normalized\cmmlu.jsonl`
- 记录数：`11917`
- 来源：`CMMLU`

## 4. 启动本地 API

```powershell
.\scripts\run.ps1
```

可选的模型支持模式：

```powershell
.\scripts\run.ps1
```

开发模式热重载：

```powershell
.\scripts\run-dev.ps1
```

模型支持模式需要 [model-provider.md](model-provider.md) 中记录的环境变量。

运行时存储相关环境变量：

- `STQB_DATABASE_URL`
- `STQB_DATABASE_PATH`
- `STQB_REDIS_URL`

完整接口清单、请求参数、响应字段、认证/权限和错误约定统一维护于[接口文档索引](../architecture/apis/README.md)；查题与 OCS 入口详见[查询与诊断 API](../architecture/apis/query.md)。本文件仅描述本地服务的运行流程、存储边界和验证方式。

钱包兑换支持 `points` 和 `days` 两类权益。天数权益会记录到期时间并只免除查题积分扣费；兑换码核销、权益变更和钱包流水在同一事务中完成。

## 5. 适配器边界

任何外部客户端都应该是围绕此稳定本地 API 的轻量级适配器。

适配器职责：

- 将外部字段名称映射为 `title`、`options` 和 `type`
- 调用本地服务
- 显示用于审核的答案、置信度和出处元数据

核心检索逻辑应保留在本地服务和搜索模块内部。

## 6. 当前启动参数

运行时通过环境变量和 uvicorn app factory 统一启动；Windows / shell 入口分别由 `run.ps1` / `run.sh` 和 `run-dev.ps1` / `run-dev.sh` 提供。

## 7. 兼容性端点

`/ocs/query` 端点将相同的查找结果包装为紧凑的 `code/data` 响应。契约见[查询与诊断 API](../architecture/apis/query.md)，接入流程见 [ocs-adapter.md](ocs-adapter.md)。

## 8. 端到端验证

- 规范化索引存在且含有记录
- 按[接口文档索引](../architecture/apis/README.md)中的查询、状态和配置接口执行健康检查
- 核对 OCS 适配器返回的 `code/data` 结构

报告将写入：

```text
data\manifests\local-service-verification.json
```

## 9. 模型兜底验证

模型兜底的主要验证方式已并入测试与运行中的真实接口检查，不再维护单独的脚本使用说明。
