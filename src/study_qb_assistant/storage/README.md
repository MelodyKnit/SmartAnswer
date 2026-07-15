# Storage 结构

该目录负责数据库、ORM、Redis 状态存储和领域仓储。

## 基础设施

- `database.py`：数据库 URL、Engine 和 Session 工厂。
- `orm.py`：集中式 SQLAlchemy 表定义；本轮结构整理不改变表结构。
- `redis_state.py`：可选 Redis 会话和事件状态，未配置时由上层使用内存实现。
- `jsonl.py`：题库 JSONL 导出。

## 领域仓储

`repositories/` 按业务聚合拆分认证、题库、令牌、使用记录、反馈、钱包、通知、公告、设置、导入脚本、权限和 LLM 数据访问。

## 约束

- 业务服务不直接操作 ORM Entity 或 SQLAlchemy Session。
- 仓储保持现有事务边界；涉及积分、令牌计数和使用日志的原子写入不得拆散。
- 默认数据库继续使用 SQLite，数据库 URL 场景继续支持 SQLAlchemy。
- 新增持久化能力时扩展所属领域仓储，不创建新的综合仓储 Facade。
