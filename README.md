# StudyQuestionBankAssistant

本项目是一个本地题库检索服务，提供：

- `GET/POST /query`
- `GET/POST /ocs/query`
- `GET /configs/ocs-local-study-bank.json`

服务端优先查本地题库，未命中时可选接入 OpenAI-compatible 大模型。

## 安装

推荐使用 Conda：

```powershell
conda env create -f environment.yml
conda activate ai-study-qb
```

## 配置

可选模型配置放环境变量，不写进 OCS 配置：

```powershell
$env:STQB_LLM_BASE_URL="https://classbot.top/v1"
$env:STQB_LLM_MODEL="gpt-5.4"
$env:STQB_LLM_API_KEY="your-api-key"
```

也可以参考示例环境 file：

- [.env.example](.env.example)

如果只用本地题库，可以不配置以上变量。

## 运行

启动服务：

```powershell
.\scripts\run.ps1
```

开发模式热重载：

```powershell
.\scripts\run-dev.ps1
```

如果希望题库未命中时调用模型：

```powershell
uvicorn study_qb_assistant.runtime:create_runtime_app --factory --host 127.0.0.1 --port 8765 --app-dir src
```

## OCS 配置

运行后可直接在 OCS 中使用：

- [configs/ocs-local-study-bank.json](configs/ocs-local-study-bank.json)

或从接口获取：

```text
http://127.0.0.1:8765/configs/ocs-local-study-bank.json
```

## 验证

健康检查：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8765/healthz"
```

查看运行状态：

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8765/status"
```

运行测试：

```powershell
python -m pytest tests -q
```

## 说明

- 提交仓库时不包含本地题库、运行日志、验证产物和私有密钥。
- 项目内保留的是服务端实现和必要的开发/验证脚本，不提交临时用户脚本补丁。
- 详细设计文档见 [docs](docs)。
