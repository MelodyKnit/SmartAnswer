# API 结构说明

该目录按“应用组装 / 数据契约 / 路由域 / 路由辅助”拆分。FastAPI 入口只负责装配应用，具体接口必须放到对应业务域目录，避免继续出现 `platform_xxx_routes.py` 这类平铺文件。

## 入口

- `local_server.py`
  - 创建 `FastAPI app`
  - 挂载运行时状态
  - 注册各业务域路由

## 数据契约

- `schemas.py`
  - 统一存放请求体 `BaseModel`
  - 请求体命名按业务意图表达，例如 `FeedbackPayload`、`ImportScriptCreatePayload`

## 路由辅助

- `context.py`
  - 当前请求上下文、鉴权判断、CORS、统一错误响应
- `query_parser.py`
  - 题目查询参数清洗与 `QuestionQuery` 构建
- `route_support.py`
  - 查题执行、日志记录、积分记账、状态与静态页面辅助

## 路由域

- `routes/auth/`
  - 登录、注册、会话、重置密码
- `routes/query/`
  - `/query`、`/ocs/query`、状态与 OCS 配置接口
- `routes/users/`
  - 用户管理、个人资料、个人看板、使用统计
- `routes/tokens/`
  - API Key 创建、更新、吊销、导入脚本快捷配置
- `routes/feedback/`
  - 用户反馈提交、反馈列表、管理员处理反馈
- `routes/wallet/`
  - 钱包、积分发放、兑换码、兑换与积分策略只读接口
- `routes/workbench/`
  - 工作台、排行统计、通知
- `routes/catalog/`
  - 角色权限与题库记录管理
- `routes/import_scripts/`
  - 导入脚本模板创建、查询、删除与生成
- `routes/llm/`
  - 大模型配置、联网搜索配置与调用统计
- `routes/system/`
  - 系统配置、系统日志与运行状态
- `routes/static/`
  - 前端静态页面分发

## 扩展约定

- 新增接口先判断资源归属，再放入对应 `routes/<domain>/__init__.py`。
- 新增业务域使用清晰的资源名目录，例如 `feedback`、`import_scripts`。
- 不再新增 `*_routes.py` 平铺文件，也不要把多个资源混进一个“platform”文件。
- 路由函数只做参数边界、鉴权、错误映射和响应组装；业务规则放在服务层。
- URL 契约以资源路径为准，整理代码结构时不要无故改变前端已使用的路径。
