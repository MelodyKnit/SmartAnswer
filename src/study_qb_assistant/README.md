# study_qb_assistant

此包是以下内容的实现基础：

- 规范问题记录架构/模式（canonical question record schemas）
- 针对特定源的导入读取器
- 未来的检索和提供商适配器

当前公共入口点：

- `CanonicalQuestionRecord`
- `QuestionQuery`
- `QueryResult`
- `AnswerService`
- `iter_cmmlu_records`
- `iter_m3ke_records`
- `iter_agieval_records`
- `LocalQuestionIndex`
- `OpenAICompatibleProvider`
