# study_qb_assistant

后端按业务职责组织，包根目录只保留运行组装、全局配置和版本信息。

## 目录边界

- `adapters/ocs/`：OCS 请求、响应、题型策略和客户端资源适配。
- `answering/`：答题编排、重试、复用、沉淀、不可作答策略和答案质量处理。
- `questions/`：题目模型、题型、标签、规范化、解析与输入校验。
- `api/`：FastAPI 应用组装、公共依赖、中间件、OCS 公共入口和版本化业务接口。
- `platform/`：令牌、使用记录、反馈、钱包、通知、公告、权限、设置等领域服务。
- `storage/repositories/`：按业务领域拆分的 SQLAlchemy 仓储；ORM 表定义仍集中在 `storage/orm.py`。
- `llm/`：模型提供者、工具、提示词、配置、调用追踪和模型管理。
- `media/`：题目图片输入、存储、图床和视觉上下文构建。
- `search/`：本地题库索引和匹配算法。
- `auth/`、`ingestion/`、`logger/`：认证、题库导入和日志基础能力。

## 公共入口

- `study_qb_assistant.AnswerService`
- `study_qb_assistant.CanonicalQuestionRecord`
- `study_qb_assistant.__version__`
- `study_qb_assistant.bootstrap.create_runtime_app`

## 约束

- 不在包根目录新增题目、答题、HTTP 或平台业务模块。
- 新业务接口放入 `api/v1/<domain>/router.py`，请求模型放入同域 `schemas.py`。
- `/ocs/query` 只由 `api/ocs` 提供，不进入版本化业务路由。
- 平台路由按领域注入服务，不依赖万能 Facade。
- 上层服务不直接操作 SQLAlchemy ORM；持久化通过领域仓储完成。
