# 运行与维护脚本

本目录只保存项目运行和部署入口。测试、测试数据初始化与人工验证脚本统一放在 [`tests/manual/`](../tests/manual/)，一次性排查输出和个人实验结果放在 `.local/`，不参与提交。

## 服务启动

- `run.ps1`：Windows PowerShell 启动入口。
- `run.sh`：Linux/macOS 启动入口。
- `--dev` 或 `-Dev`：启用 Uvicorn 热重载；开发模式仅监听 `src/study_qb_assistant`，避免运行数据和前端文件触发无意义重启。

示例：

```powershell
.\scripts\run.ps1
.\scripts\run.ps1 --dev
```

```bash
./scripts/run.sh
./scripts/run.sh --dev
```

## 约束

- 启动脚本依赖项目定义的 Conda 环境，不安装或修改全局 Python 依赖。
- 生产部署使用根目录 `docker-compose.yaml`。
- 新增运行或部署入口时，在本页补充用途、前置条件和数据影响范围。
