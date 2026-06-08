# Platform 结构说明

该目录负责平台领域能力，当前按“服务 / 记录 / 配置 / 存储”拆分：

- `service.py`
  - API 令牌
  - 积分计费
  - 使用日志
  - 反馈
  - 钱包与兑换码
  - 系统配置
- `records.py`
  - 平台状态落盘时使用的记录模型
- `config.py`
  - 平台系统配置字段与环境变量映射常量
- `storage.py`
  - 平台令牌的序列化、安全脱敏与公开视图辅助

## 设计约束

- 对外统一从 `study_qb_assistant.platform` 导入 `PlatformService`
- `service.py` 负责业务规则与状态编排
- `records.py` 只负责状态记录结构，不承担业务判断
- `config.py` 只负责配置常量定义，不承载业务逻辑
- 平台数据实际持久化由 SQLAlchemy 仓储层负责，默认数据库为 SQLite

## 扩展建议

- 新增平台持久化对象，先补到 `records.py`
- 新增平台业务操作，放到 `service.py`
- 新增系统配置项时，先同步更新 `config.py`
- 新增平台状态读写规则时，优先落到 `storage.py`
- 若后续钱包、反馈或计费继续膨胀，可再细分为子服务，但先保持一个清晰 Facade 入口
