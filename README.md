# StudyQuestionBankAssistant

自托管的学习型题库与 AI 服务平台。它提供本地题库检索、模型辅助答题、联网检索、题目图片处理、API Key 接入、积分与运营管理，以及私有 AI 生图能力。

项目面向学习、复核和知识管理场景。服务负责提供检索结果、答案建议和来源信息，不包含自动提交课程、考试或作业答案的能力。

## 功能概览

- 题库检索：标准化题目、选项与答案，支持本地精确和保守模糊匹配。
- AI 答题：本地题库优先，模型兜底，必要时使用联网证据增强。
- OCS 接入：保留 `/ocs/query` 兼容入口，并由管理端生成 API Key 对应配置。
- 平台管理：用户、角色权限、API Key、积分、兑换码、公告、通知和调用记录。
- 图片处理：题目图片与生图资产均使用受控存储，不将 Base64 或密钥写入日志。
- AI 生图：支持文本生图和受模型能力约束的图片编辑，任务、积分与资产生命周期独立管理。

## 快速开始

项目使用 Conda 管理 Python 环境，前端使用 npm。

```powershell
conda env create -f environment.yml
conda activate ai-study-qb
Copy-Item .env.example .env
.\scripts\run.ps1
```

开发模式只监听后端源码目录：

```powershell
.\scripts\run.ps1 --dev
```

Linux/macOS：

```bash
./scripts/run.sh
./scripts/run.sh --dev
```

默认服务地址为 `http://127.0.0.1:8765`。前端开发与环境变量配置见[环境与依赖说明](docs/setup/environment.md)。

## 常用验证

```powershell
conda run -n ai-study-qb pytest -q
conda run -n ai-study-qb ruff check src tests
conda run -n ai-study-qb mypy src/study_qb_assistant

Set-Location src\website
npm run type-check
npm run build
```

健康检查：

- 平台 API：`GET /api/v1/healthz`
- OCS 兼容查询：`GET|POST /ocs/query`

## 部署与数据

- Docker Compose 使用仓库根目录的 `docker-compose.yaml`；详细步骤见[部署说明](docs/deployment.md)。
- 运行数据、SQLite 数据库、日志和图片资产位于配置的数据目录，Docker 默认通过 `deploy-data` 卷持久化。
- `.env`、数据库、运行数据、日志、图片和本地实验目录均不得提交。部署前仅复制并填写 `.env.example` 中实际需要的配置。

## 文档导航

完整导航见[docs/README.md](docs/README.md)。常用入口：

- [环境与依赖](docs/setup/environment.md)
- [系统架构](docs/architecture/architecture.md)
- [API 契约](docs/architecture/api-contract.md)
- [模型与联网服务](docs/services/model-provider.md)
- [OCS 适配](docs/services/ocs-adapter.md)
- [图片生成服务](docs/services/image-generation.md)
- [后端目录边界](src/study_qb_assistant/README.md)
- [运行与维护脚本](scripts/README.md)

## 发布约定

正式发布时同步更新 `pyproject.toml` 版本号、提交版本变更并创建同名 Git tag。服务器部署使用经过验证的发布版本；本地未提交实验和运行数据不进入发布物。

## License

项目许可证见 [LICENSE](LICENSE)。
