# API 结构说明

该目录按“应用组装 / 数据契约 / 路由域 / 路由辅助”拆分，避免把所有 FastAPI 代码继续堆在一个入口文件里。

## 入口

- `local_server.py`
  - 只负责创建 `FastAPI app`
  - 挂载运行时状态
  - 注册各业务域路由

## 数据契约

- `schemas.py`
  - 所有请求体 `BaseModel`

## 路由辅助

- `context.py`
  - 当前请求上下文、鉴权判断、CORS、统一错误响应
- `query_parser.py`
  - 题目查询参数清洗与 `QuestionQuery` 构建
- `route_support.py`
  - 查题执行、日志记录、积分记账、状态与静态页面辅助

## 路由域

- `routes/auth_routes.py`
  - 登录、注册、会话、重置密码
- `routes/query_routes.py`
  - `/query`、`/ocs/query`、状态与配置接口
- `routes/platform_routes.py`
  - 平台域组合入口
- `routes/platform_user_routes.py`
  - 用户中心、使用日志、反馈、个人看板
- `routes/platform_admin_routes.py`
  - 用户管理、令牌管理、计费与系统配置
- `routes/platform_wallet_routes.py`
  - 钱包、人工充值、兑换码与兑换
- `routes/static_routes.py`
  - 前端静态页面分发

## 扩展约定

- 新增请求体先放进 `schemas.py`
- 新增路由先判断属于哪个业务域，再放入对应 `routes/*.py`
- 与多个路由共享的逻辑，优先放入 `context.py` 或 `route_support.py`
- `local_server.py` 不再承载业务细节，只保留应用装配职责
