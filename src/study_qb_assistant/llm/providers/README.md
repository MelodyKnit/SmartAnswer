# LLM Providers 结构说明

该目录负责模型提供者与联网搜索增强相关能力。

## 文件职责

- `base.py`
  - 提供统一的模型提供者接口约束
- `openai_compatible.py`
  - OpenAI 兼容模型提供者入口
  - 负责请求编排、提示词组织、日志记录
- `openai_answer_parser.py`
  - 模型响应解析
  - SSE 解码
  - 候选答案标准化
- `web_search.py`
  - 搜索提供者主入口与多提供者组合
- `web_search_http.py`
  - 搜索请求的 HTTP 访问与 DuckDuckGo 结果展开辅助
- `web_search_types.py`
  - 搜索结果数据结构与提供者协议

## 设计约束

- `openai_compatible.py` 保持为提供者入口，不再堆积底层解析细节
- 模型响应解析与格式兼容逻辑优先放入 `openai_answer_parser.py`
- 搜索提供者入口、HTTP 访问与共享类型保持分层，不再堆到单个 `web_search.py`
- 对外统一从 `study_qb_assistant.llm.providers` 导入主提供者
- 搜索证据增强编排属于 `study_qb_assistant.llm.orchestration`

## 扩展建议

- 新增模型协议适配器时，优先复用 `base.py` 的抽象边界
- 若后续响应解析规则继续增长，应继续保持“请求入口”和“解析逻辑”分离
