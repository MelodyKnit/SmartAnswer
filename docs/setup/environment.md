# 环境配置

更新日期：`2026-06-07`

## 1. 工具链决策

本项目使用 `Conda` 作为项目级别的 Python 环境管理器。

原因：

- 工作区对 Python 项目的规则要求
- 足以支持当前轻量级的 FastAPI 服务
- 保持运行依赖在项目级别是显式声明的

## 2. 环境配置文件

主要文件：

- [environment.yml](../environment.yml)

## 3. 引导命令

创建环境：

```powershell
conda env create -f environment.yml
```

激活环境：

```powershell
conda activate ai-study-qb
```

## 4. 当前验证命令

运行当前的样本测试：

```powershell
python -m pytest tests -q
```

当前验证的环境：

- Conda 环境：`ai-study-qb`
- 最终验证是在 `ai-study-qb` 环境中运行的
- 最新结果：`61` 个单元测试通过，FastAPI 本地服务验证通过，以及模拟模型回退验证通过

## 5. 运行时依赖

当前有意添加的运行时/测试依赖项：

- `fastapi`：成熟的路由处理、请求验证和 ASGI 集成
- `httpx`：成熟的同步 HTTP 客户端，用于模型/搜索请求、代理支持、超时和状态错误处理
- `python-dotenv`：健壮的 `.env.local` 解析，同时保留现有的进程变量
- `uvicorn`：FastAPI 本地服务的 ASGI 运行环境，支持开发热重载
- `pytest`：项目测试运行器

## 6. 未来依赖策略

当添加新的依赖时：

- 更新 `environment.yml`
- 保持依赖列表最简化
- 记录为什么需要每个新依赖

## 7. 模型提供商环境

可选的模型后端服务模式读取以下变量：

- `STQB_LLM_BASE_URL`
- `STQB_LLM_MODEL`
- `STQB_LLM_API_KEY`
- `STQB_LLM_PROXY`
- `STQB_WEB_SEARCH_PROVIDER`
- `STQB_SEARCH_PROXY`
- `STQB_AI_CACHE_ENABLED`
- `STQB_AI_CACHE_PATH`
- `STQB_AI_CACHE_MIN_CONFIDENCE`
- `STQB_AI_CACHE_MIN_CONFIRMATIONS`

API 密钥特意不存储在项目文件中。默认的 AI 已学题库路径为 `data\normalized\ai-learned.jsonl`；它以常规的 `CanonicalQuestionRecord` JSONL 行格式存储 AI 生成的答案，并带有 `ai_generated` 和 `auto_learned` 标签。当启用基于模型学习的模式时，遗留的 `data\runtime\ai-answer-cache.json` 文件将作为兼容性迁移源进行读取。
