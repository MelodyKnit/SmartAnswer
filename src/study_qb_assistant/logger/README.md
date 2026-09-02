# Logger 结构说明

该目录负责运行时结构化日志，当前按“入口 / 控制台 / 存储”拆分：

- `__init__.py`
  - `log_event`
  - `recent_events`
  - `configure_external_loggers`
- `console.py`
  - 控制台格式器
  - 事件到 logger / level / 文本摘要的映射
- `storage.py`
  - 日志路径
  - 敏感字段脱敏
  - 日志保留时间与容量策略的限频清理

## 设计约束

- 对外统一从 `study_qb_assistant.logger` 导入
- `console.py` 不负责磁盘写入
- `storage.py` 不负责日志级别与格式映射
- `__init__.py` 负责串联内存队列、控制台输出与 JSONL 落盘
- 控制台日志通过管理端读取时会对 Bearer、Token、密码和 API Key 等敏感值脱敏
- 日志清理策略从系统配置读取，清理失败不会影响业务请求或日志写入
