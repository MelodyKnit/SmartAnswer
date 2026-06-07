# 研究笔记

更新时间：`2026-06-07`

## 1. 项目定位

目标功能：

- 接收一个包含 `title`、`options` 和 `type` 等字段的规范化题目负载
- 从维护的题库中检索匹配的内容
- （可选地）调用本地或自托管的 LLM 进行答案规范化和解释说明
- 返回候选答案、解释和来源以供人工审核

优选成果：

- 具有稳定 API 的、易维护的本地服务
- 可复用的题库导入与索引机制
- 基于来源证据的答案，而非原始的模型猜测

非本项目目标：

- 自动提交答案
- 绕过平台限制的相关工作
- 依赖稳定性未知的封闭第三方答案 API

## 2. OCS API 笔记

官方参考资料：

- <https://docs.ocsjs.com/docs/other/api/>
- <https://docs.ocsjs.com/docs/work>
- OCS 官方仓库：<https://github.com/ocsjs/ocsjs>

开发者文档中的关键接口细节：

- OCS 题库配置是一个数据源定义的数组。
- 数据源定义可以包括 `url`、`method`、`contentType`、`data` 和 `handler`。
- `url` 和 `data` 支持占位符替换。
- 支持的已文档化占位符包括 `${title}`、`${type}` 和 `${options}`。
- `handler` 用于将响应映射为 OCS 所期望的答案结构。
- `data` 内部的第一级字段可以使用基于自定义 handler 的解析。
- 文档中还提到了一个全域名开发版本，用于支持广泛的跨域请求。

对本项目的实际指导意义：

- 我们未来的服务应该暴露出一个干净的 HTTP 接口，该接口能够接收规范化的题目字段
- 服务响应应当易于映射到外部客户端的 handler 中
- 核心价值应该体现在我们的检索和证据管道中，而不是客户端专属的粘合代码上

## 3. 候选开源平台

### 第一梯队：目前最强候选

1. `MaxKB`
- GitHub：<https://github.com/1Panel-dev/MaxKB>
- 文档：<https://docs.maxkb.pro/>
- 为什么脱颖而出：
  - 专为企业级智能体和 RAG 设计
  - 支持本地和托管模型
  - 支持通过离线文档、表格、QA 对和网站构建知识库
  - 暴露出兼容 OpenAI 的应用 API
- 研究笔记：
  - 官方文档称 MaxKB 支持离线文档、表格、QA 对和网站知识库
  - 官方文档还描述了兼容 OpenAI 的聊天端点，并支持 Ollama/OpenAI 风格的模型提供商
- 适合本项目的地方：
  - 如果我们想要快速获得易于维护的 UI、知识导入和应用 API，这是非常好的选择

2. `FastGPT`
- GitHub：<https://github.com/labring/FastGPT>
- 文档：<https://doc.fastgpt.io/en/docs/introduction>
- 为什么脱颖而出：
  - 知识库优先的架构
  - 强大的可视化工作流编排
  - 多种导入模式，包括手动 QA 对和 CSV 导入
  - 专为问答系统设计
- 研究笔记：
  - 官方文档将其描述为具有 RAG 检索和可视化工作流编排的知识库问答系统
  - 知识库文档包括手动 QA 输入、QA 拆分、直接分块和 CSV 导入
- 适合本项目的地方：
  - 如果我们想要显式的 QA 对管理以及工作流控制，这是最强有力的选择

3. `Open WebUI`
- GitHub：<https://github.com/open-webui/open-webui>
- 文档：<https://docs.openwebui.com/features/workspace/knowledge/>
- 为什么脱颖而出：
  - 简单的本地部署路径
  - 与 Ollama 配合默契
  - 知识库支持包括混合检索和 API 管理
- 研究笔记：
  - 官方文档展示了支持文件上传、检索模式和 REST API 的知识库
- 适合本项目的地方：
  - 最好的轻量级原型路径，但作为结构化题库后端的表现弱于 MaxKB/FastGPT

### 第二梯队：强大但较重或更专用

4. `Dify`
- GitHub：<https://github.com/langgenius/dify>
- 文档：<https://docs.dify.ai/en/guides/knowledge-base/readme>
- 适合：
  - 如果我们后续相比于直接的 QA 对操作，需要更多的工作流和应用编排，这是不错的选择

5. `RAGFlow`
- GitHub：<https://github.com/infiniflow/ragflow>
- 适合：
  - 适用于复杂的文档解析和高级 RAG，但对于首次构建来说偏重

6. `QAnything`
- GitHub：<https://github.com/netease-youdao/QAnything>
- 适合：
  - 强大的本地知识库项目，尤其是当文档问答比显式题库结构更重要时

7. `Langchain-Chatchat`
- GitHub：<https://github.com/chatchat-space/Langchain-Chatchat>
- 适合：
  - 灵活的本地 RAG 栈，具有广泛的模型兼容性，但更偏向工程导向而非产品导向

## 4. 本地模型服务选择

### 推荐的服务层

1. `Ollama`
- 文档：<https://docs.ollama.com/api/openai-compatibility>
- 原因：
  - 适合首个原型最简单的本地模型运行时
  - 官方支持 OpenAI 兼容性

2. `LM Studio`
- 文档：<https://lmstudio.ai/docs/developer/core/server>
- 原因：
  - 易于基于 GUI 进行本地服务
  - 官方文档暴露了兼容 OpenAI 的端点

3. `vLLM`
- 文档：<https://docs.vllm.ai/en/latest/serving/openai_compatible_server/>
- 原因：
  - 后期更佳的高性能服务路径
  - 在服务形态稳定后更为适用

## 5. 公共题库和基准测试源

这些资源可用作种子数据、评估集或模式（schema）参考。它们并不全是生产就绪的答案库，在导入前必须检查许可协议。

1. `C-Eval`
- 仓库：<https://github.com/hkust-nlp/ceval>
- 说明：
  - 官方仓库描述了涵盖 `52` 个学科的 `13,948` 道多项选择题
  - 数据集可以从 Hugging Face 加载
  - 可用作结构化的 MCQ 种子数据和评估材料

2. `CMMLU`
- 仓库：<https://github.com/haonan-li/CMMLU>
- 说明：
  - 官方仓库描述了一个涵盖 `67` 个主题的中文基准测试
  - 适用于中文知识领域的覆盖与评估

3. `M3KE`
- 仓库：<https://github.com/tjunlp-lab/M3KE>
- 说明：
  - 官方仓库声明了来自 `71` 个任务的 `20,477` 道题目
  - 涵盖了小学到大学以及多个学科
  - 可用作大规模的结构化 MCQ 材料

4. `CMMMU`
- 仓库：<https://github.com/CMMMU-Benchmark/CMMMU>
- 说明：
  - 包含中文题目材料的多模态基准测试
  - 仅在需要图片题目支持时才适用

5. `AGIEval`
- 仓库：<https://github.com/ruixiangcui/AGIEval>
- 说明：
  - 可用作评估数据和基准测试参考
  - 更广泛的基准测试，与上述三者相比，较少直接针对本地中文学习内容进行定制

## 6. 当前实现决策

项目目前使用自定义的 Python 本地服务，而不是采用 MaxKB、FastGPT 或 Open WebUI 作为主要运行时。

原因：

- 最终需要的输出是一个调用固定本地端口的 OCS 风格数据源配置
- 轻量级的自定义服务对响应结构、handler 兼容性和来源元数据提供了更紧密的控制
- 兼容 OpenAI 的提供商抽象使得云端 API 和本地模型运行时均可使用
- 公共基准测试数据可以直接规范化为项目拥有的 JSONL 索引

如果后续管理 UI、大规模文档导入或可视化工作流层变得更加重要，MaxKB、FastGPT 和 Open WebUI 仍然是有用的。

## 7. 具有产品 UI 需求时的平台选择

如果后续需要产品导向的层级，请评估：

1. `MaxKB + Ollama`
- 本地部署、QA 导入、网站/文档同步以及 API 兼容性之间的最佳平衡

如果想要稍多一些的工作流灵活性：

2. `FastGPT + Ollama`
- 尤其是当源数据将被转化为 QA 对或 CSV 导入时非常适用

如果在投入使用前需要一个极简原型：

3. `Open WebUI + Ollama`
- 适合在构建更结构化的后端之前验证检索和本地模型路径

在所有情况下，Ollama 都可以被任何兼容 OpenAI 的云端或自托管模型端点所替代。

## 8. 外部题库 API 策略

未知的免费搜索 API 或爬取网站不应作为默认依赖。在网上找到的大多数公共网页片段并不能提供足够的证据来证明其具有：

- 稳定的 API 契约
- 重新分发或使用许可
- 来源归属
- Token 安全性
- 长期可用性

该架构为未来的来源保留了外部源适配器边界，要求其具有明确的许可和已文档化的 API 契约。

## 9. 建议的架构方向

阶段 1：

- 选择一个平台
- 定义规范化的题目 schema
- 导入一个简易且干净的样题库
- 通过人工审核验证检索质量

阶段 2：

- 添加由检索证据支持的解释生成
- 添加来源归属和答案置信度信号
- 支持从 CSV/XLSX/JSON 进行结构化导入

阶段 3：

- 暴露出一个稳定的本地 HTTP API
- 针对 schema 映射、检索和答案格式化添加测试
- 决定是否仍然需要外部客户端适配器

## 10. 最终架构栈的筛选标准

在锁定架构栈之前，使用这些标准进行评估：

- 可以直接导入 QA 对
- 可以保留原始来源字段和标签
- 干净地支持本地模型服务
- 支持引用或来源追踪
- 稳定的 API 接口
- 简便的备份/导出路径
- 可接受的 Windows 部署体验

## 11. 紧迫的下一步工作

推荐的下一步行动：

- 从用户真实的 OCS 环境验证本地服务

原因：

- 本地自动化的配置客户端验证器已经通过
- 剩下的不确定性是真实的用户脚本/客户端运行时以及用户选择的模型端点
