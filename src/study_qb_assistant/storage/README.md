# Storage 结构说明

该目录负责 SQLAlchemy 与 Redis 基础设施层。

## 文件职责

- `database.py`
  - 数据库 URL 解析
  - Engine / Session 工厂
  - 默认 SQLite 入口
- `orm.py`
  - SQLAlchemy ORM 表定义
- `auth_repository.py`
  - 用户数据仓储
- `llm_repository.py`
  - 大模型配置、调用追溯和模型调用统计仓储
- `platform_repository.py`
  - 平台状态兼容 Facade，仍保留未独立拆分的平台领域读写入口
- `question_repository.py`
  - 题库管理和 AI 沉淀题库仓储
- `redis_state.py`
  - Redis 客户端构建
  - 会话存储
  - 最近事件存储

## 设计约束

- 上层业务服务不直接操作 SQLAlchemy ORM 细节
- 默认数据库使用 SQLite
- Redis 是可选状态层，未配置时回退到内存实现
- 业务层优先依赖仓储与状态存储抽象，而不是直接读写文件
- 新增或迁移平台数据读写时，优先参考 `llm_repository.py` 的领域仓储拆分方式
- `platform_repository.py` 只作为兼容聚合入口继续存在，不应继续扩展成新的巨石仓储
