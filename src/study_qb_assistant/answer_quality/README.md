# Answer Quality 结构说明

该目录负责模型答案修复与高信号规则匹配，当前按“入口 / 规则 / 辅助”拆分：

- `__init__.py`
  - `direct_known_answer`
  - `repair_model_answer`
  - `is_cache_safe_answer`
- `rules.py`
  - 外部规则文件加载
  - 已知选择题 / 填空题规则匹配
- `support.py`
  - 标签映射
  - 判断题修复
  - 解释文本与答案文本互相推导

## 设计约束

- 对外统一从 `study_qb_assistant.answer_quality` 导入
- `rules.py` 只负责规则读取与已知命中
- `support.py` 只负责答案结构修复与映射
- `__init__.py` 保持高层入口，不继续堆底层正则与规则文件处理
