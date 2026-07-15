# LLM 工具模块

`llm.tools` 统一管理可参与答题编排的外部能力，但不拥有题库索引或模型实现。

- `LocalRagTool` 适配 `search.LocalQuestionIndex`，匹配算法仍由 `search` 包维护。
- `WebSearchTool` 适配联网搜索提供者，搜索引擎、HTTP 与 Playwright 实现位于
  `llm.tools.web_search`。
- `LlmToolRegistry` 按稳定名称和能力注册工具，重复名称会被拒绝。
- 内部实现继承 `AnswerRetrievalTool` 或 `EvidenceRetrievalTool`；测试替身和第三方
  扩展可实现 `llm.contracts` 中的 Protocol，无需继承项目基类。

新增工具时应声明单一、明确的能力，不应在工具层修改答题置信度、积分或题库沉淀策略。
