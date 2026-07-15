# OCS 集成模块

`adapters.ocs` 是 OCS 请求与本项目内部答题模型之间的适配边界。

- `DefaultOcsIntegration` 是 API 层默认使用的 Facade。
- `OcsIntegrationPort` 允许测试或第三方实现替换默认集成。
- `OcsQuestionTypeRegistry` 管理题型策略，新增平台题型时实现
  `BaseOcsQuestionTypeHandler` 并注册即可。
- `resources/` 保存可随 Python 包发布的导入模板和客户端桥接脚本。

官方题型 `single`、`multiple`、`judgement`、`completion` 具有专用答案格式。
`reader`、`line` 等平台私有题型会保留原始类型并标记为 `unsupported`，不会被错误映射。
