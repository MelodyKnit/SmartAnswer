# OCS 集成模块

`adapters.ocs` 是 OCS 请求与本项目内部答题模型之间的适配边界。

- `DefaultOcsIntegration` 是 API 层默认使用的 Facade。
- `OcsIntegrationPort` 允许测试或第三方实现替换默认集成。
- `OcsQuestionTypeRegistry` 管理题型策略，新增平台题型时实现
  `BaseOcsQuestionTypeHandler` 并注册即可。
- `resources/` 保存随 Python 包发布的 OCS v2 POST 配置模板，Token、公开配置、分享页和管理模板统一使用它。
- `images.py` 在通用解析前校验图片编号与内联数据，去重图片时同步重映射题干/选项编号；错误输入由路由返回 `400 INVALID_INPUT`。
- 请求内部保留去重后图片到原编号的映射，OCS 响应恢复客户端原编号，以兼容客户端将答案图片占位符还原为 URL 的行为。

官方题型 `single`、`multiple`、`judgement`、`completion` 具有专用答案格式。
`reader`、`line` 等平台私有题型会保留原始类型并标记为 `unsupported`，不会被错误映射。

请求字段和图片输入约束见 [查询与诊断 API](../../../../docs/architecture/apis/query.md)。含 `[图片N]` 的查询不能按占位文本复用历史答案；视觉消息显式标注每张图片编号。回归入口：`tests/test_ocs_config.py`（执行真实 JavaScript 字段处理器）、`tests/test_ocs_config_api.py`（各配置出口和请求边界）、`tests/test_ocs_image_import.py`（水合、编号和缓存隔离）。
