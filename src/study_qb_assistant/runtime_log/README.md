# Runtime Log 结构说明

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

## 设计约束

- 对外统一从 `study_qb_assistant.runtime_log` 导入
- `console.py` 不负责磁盘写入
- `storage.py` 不负责日志级别与格式映射
- `__init__.py` 负责串联内存队列、控制台输出与 JSONL 落盘
