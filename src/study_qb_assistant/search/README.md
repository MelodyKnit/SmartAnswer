# Search 结构说明

该目录负责本地标准题库检索，当前按“入口 / 辅助”拆分：

- `__init__.py`
  - `LocalQuestionIndex`
  - 本地精确匹配与模糊匹配主流程
- `support.py`
  - JSONL 记录读取
  - AI 自动沉淀题标记判断
  - 元数据数值解析
  - 选项一致性辅助

## 设计约束

- 对外统一从 `study_qb_assistant.search` 导入 `LocalQuestionIndex`
- `support.py` 只负责小型辅助函数
- `__init__.py` 保持检索主流程与结果构造，不继续堆文件读取和状态判断杂项
