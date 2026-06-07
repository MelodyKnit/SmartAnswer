# 题库与学习助手文档中心

欢迎使用 StudyQuestionBankAssistant 文档中心。为了保持文档的可读性，所有的开发、架构、API 规范以及配置指南已被分类整理存放在以下子目录中。

---

## 目录索引 (Documentation Index)

### 🛠️ 1. 环境安装与数据配置 (Setup & Data)
记录如何配置项目环境、导入题库并校验数据完整性。
*   [docs/setup/environment.md](setup/environment.md) —— Conda 开发环境配置、环境变量说明与运行时依赖。
*   [docs/setup/data-sources.md](setup/data-sources.md) —— 本地题库支持的公开评测集（C-Eval, CMMLU 等）源策略说明。
*   [docs/setup/normalized-indexes.md](setup/normalized-indexes.md) —— 规整化数据输出 `.jsonl` 索引格式及大小。
*   [docs/setup/source-verification.md](setup/source-verification.md) —— 数据集开源协议、可信度评估及本地获取状态。
*   [docs/setup/ingestion-mapping.md](setup/ingestion-mapping.md) —— 不同数据集（如 CMMLU 的 CSV 或 AGIEval 的 JSON）到统一 schema 的映射细节。

### 🏗️ 2. 系统架构与设计规范 (Architecture & Design)
系统的总体架构流图、核心接口规范及用户认证设计。
*   [docs/architecture/architecture.md](architecture/architecture.md) —— 系统总体流程（归一化 -> 决策 -> 本地索引 -> RAG 网页搜索 -> 大模型 Fallback -> 人工审核）及架构。
*   [docs/architecture/system-design-specification.md](architecture/system-design-specification.md) —— **系统核心设计说明书**，包含用户登录、注册、邀请码认证机制，SQL 数据库表设计以及 OCS API 密钥安全策略。
*   [docs/architecture/api-contract.md](architecture/api-contract.md) —— 本地问答查询接口的正规 JSON 格式与错误码协议契约。
*   [docs/architecture/stack-decision.md](architecture/stack-decision.md) —— 技术选型决策与 Phase 1 核心范围定义。

### ⚙️ 3. 业务服务与客户端适配器 (Services & Adapters)
了解系统具体的服务逻辑以及如何对接第三方客户端（如 Tampermonkey 油猴插件）。
*   [docs/services/local-service.md](services/local-service.md) —— 本地极简 HTTP 查题服务器运行逻辑与命令。
*   [docs/services/model-provider.md](services/model-provider.md) —— OpenAI 兼容的大模型适配、网页搜索 RAG 编排器以及 AI 缓存晋升细节。
*   [docs/services/ocs-adapter.md](services/ocs-adapter.md) —— 原生 OCS-Style 接口兼容适配（`/ocs/query`）及静态配置分发。
*   [docs/services/external-client-adapter.md](services/external-client-adapter.md) —— 对外服务 CORS 跨域请求与客户端调用参数映射。
*   [docs/services/ocs-usage-cn.md](services/ocs-usage-cn.md) —— **油猴 OCS 插件客户端使用指南**，手把手教您如何填入配置和 API 密钥进行查题。

### 📋 4. 研发流程、测试与交付 (Process, Tests & Delivery)
说明研究背景、测试覆盖度以及当前保留的实现说明。
*   [docs/process/research.md](process/research.md) —— 先期可行性调研日志、开源知识库管理（MaxKB, FastGPT）及本地推理引擎评估。
*   [docs/process/implementation-plan.md](process/implementation-plan.md) —— 项目实施路线图、里程碑拆解与技术风险评估。
*   [docs/process/acceptance.md](process/acceptance.md) —— 当前自动化测试与验收边界说明。
