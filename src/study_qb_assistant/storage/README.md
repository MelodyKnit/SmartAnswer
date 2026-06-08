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
- `platform_repository.py`
  - 平台状态仓储
- `redis_state.py`
  - Redis 客户端构建
  - 会话存储
  - 最近事件存储

## 设计约束

- 上层业务服务不直接操作 SQLAlchemy ORM 细节
- 默认数据库使用 SQLite
- Redis 是可选状态层，未配置时回退到内存实现
- 业务层优先依赖仓储与状态存储抽象，而不是直接读写文件
