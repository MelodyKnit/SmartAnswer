# study_qb_assistant

此包是本项目的核心实现，当前按领域边界组织：

- `api/`
  - FastAPI 应用组装、请求模型、路由与上下文辅助
- `adapters/`
  - OCS 协议适配与配置生成
- `llm/`
  - 大模型提供者、联网搜索增强、模型配置、调用追踪与 LLM 答案缓存
- `answering/`
  - 答题决议编排、AI 异常重试、答案沉淀与不可作答策略
- `answer_quality/`
  - 模型答案修复、高信号规则匹配与标签映射
- `auth/`
  - 本地账号鉴权、会话、密码重置与积分扣减
- `platform/`
  - API 令牌、计费、反馈、钱包、系统配置
- `logger/`
  - 结构化日志、控制台格式器与敏感信息脱敏
- `media/`
  - 题目图片上下文装载、图片资产存储、本地图床与图片不可读策略
- `search/`
  - 本地题库检索索引与检索辅助
- `storage/`
  - SQLAlchemy ORM、数据库仓储与 Redis 状态存储
- `ingestion/`
  - 外部题库导入读取器

仍保留在包根目录的模块，原则上应满足“跨领域共享且职责单一”：

- `runtime.py`
  - 运行时服务组装入口
- `models.py`
  - 核心数据结构
- `http_client.py`
  - 统一 HTTP 请求封装
- `normalization.py`
  - 基础文本标准化
- `option_labels.py`
  - 选项标签规整
- `exporting.py`
  - 标准题库导出辅助
- `image_ocr.py`
  - 图片题旧导入兼容入口，新代码应使用 `media.question_context`
- `input_anomalies.py`
  - 进入答题流程前的输入异常识别，不承载模型答案质量策略

## 关键公共入口

- `CanonicalQuestionRecord`
- `QuestionQuery`
- `QueryResult`
- `AnswerService`
- `LocalQuestionIndex`
- `OpenAICompatibleProvider`

## 设计约束

- 包根目录只保留真正跨领域共享的核心模块
- 领域内的数据记录、服务实现和辅助工具优先放入对应子目录
- 大模型相关实现统一放入 `llm/`，不要在顶层新增 `providers` 或 `ai_*` 包
- 运行日志统一放入 `logger/`
- 当某个文件开始同时承担“入口 + 解析 + 规则 + 存储”多种职责时，应优先拆分
