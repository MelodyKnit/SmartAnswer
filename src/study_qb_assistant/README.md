# study_qb_assistant

此包是本项目的核心实现，当前按领域边界组织：

- `api/`
  - FastAPI 应用组装、请求模型、路由与上下文辅助
- `adapters/`
  - OCS 协议适配与配置生成
- `ai_answer_cache/`
  - AI 自动沉淀题库状态机、记录模型与缓存辅助
- `answer_quality/`
  - 模型答案修复、高信号规则匹配与标签映射
- `auth/`
  - 本地账号鉴权、会话、密码重置与积分扣减
- `platform/`
  - API 令牌、计费、反馈、钱包、系统配置
- `providers/`
  - 模型提供者、响应解析、联网搜索增强
- `runtime_log/`
  - 结构化日志、控制台格式器与敏感信息脱敏
- `search/`
  - 本地题库检索索引与检索辅助
- `storage/`
  - SQLAlchemy ORM、数据库仓储与 Redis 状态存储
- `ingestion/`
  - 外部题库导入读取器

仍保留在包根目录的模块，原则上应满足“跨领域共享且职责单一”：

- `answering.py`
  - 题目答案决议编排入口
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

## 关键公共入口

- `CanonicalQuestionRecord`
- `QuestionQuery`
- `QueryResult`
- `AnswerService`
- `LocalQuestionIndex`
- `OpenAICompatibleProvider`

## 设计约束

- 包根目录尽量只保留真正跨领域共享的核心模块
- 领域内的数据记录、服务实现和辅助工具优先放入对应子目录
- 当某个文件开始同时承担“入口 + 解析 + 规则 + 存储”多种职责时，应优先拆分
