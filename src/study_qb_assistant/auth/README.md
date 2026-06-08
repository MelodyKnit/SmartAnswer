# Auth 结构说明

该目录负责本地账号鉴权能力，按“服务 / 记录 / 安全工具”拆分：

- `service.py`
  - 账号注册、登录、会话解析、密码重置、积分扣减
- `records.py`
  - `UserRecord`
  - `SessionRecord`
- `security.py`
  - 密码哈希
  - 令牌摘要
  - 用户名、密码、节流相关常量

## 设计约束

- 用户数据持久化由 SQLAlchemy 负责，默认数据库为 SQLite
- 会话状态优先使用 Redis，未配置时回退为内存实现
- 对外统一从 `study_qb_assistant.auth` 导入 `AuthService` 与 `AuthError`

## 扩展建议

- 新增持久化字段时，先同步更新 `records.py`
- 新增密码或节流策略时，优先放到 `security.py`
- `service.py` 保持为业务编排层，不继续堆底层常量与数据记录定义
