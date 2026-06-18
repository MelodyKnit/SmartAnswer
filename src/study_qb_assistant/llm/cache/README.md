# LLM Answer Cache 结构说明

该目录负责 LLM 自动沉淀题库能力，当前按“服务 / 记录 / 辅助”拆分：

- `__init__.py`
  - `LlmAnswerCache`
  - `cache_key`
  - 对外主入口
- `records.py`
  - `CachedLlmAnswer`
  - LLM 沉淀题的统一记录模型
- `support.py`
  - 缓存键相关辅助
  - 候选答案格式校验
  - 字段值安全解析

## 设计约束

- 对外统一从 `study_qb_assistant.llm.cache` 导入
- `__init__.py` 负责状态机、持久化协调与兼容导出
- `records.py` 只负责记录结构和题库记录转换
- `support.py` 只负责辅助判断与小型纯函数

## 扩展建议

- 新增 LLM 沉淀记录字段时，优先修改 `records.py`
- 新增缓存校验规则时，优先落到 `support.py`
- `__init__.py` 避免继续堆放与状态机无关的辅助逻辑
