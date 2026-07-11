# 大模型提示词模板

本目录存放所有直接发送给大模型的静态提示词模板，统一使用 Jinja 语法。

## 文件说明

- `answer_system.jinja`：通用答题 System Prompt。
- `answer_user.jinja`：题目、选项、题型输出格式、联网证据和上一轮答案的 User Prompt。
- `answer_with_evidence_system_append.jinja`：有联网证据时追加的 System Prompt。
- `answer_verification_system_append.jinja`：复核已有答案时追加的 System Prompt。
- `llm_connection_test_user.jinja`：大模型配置页测试连接使用的题目。

## 修改约定

- 模板变量由代码固定传入，变量名写错会触发运行错误。
- 不要在模板中写入 API Key、账号、真实用户数据或服务器私有地址。
- 修改输出 JSON 字段要求时，需要同步更新模型解析和相关测试。
