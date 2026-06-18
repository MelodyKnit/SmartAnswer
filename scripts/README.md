# Scripts

本目录只保留项目运行入口：

- `run.ps1` / `run.sh`：生产模式启动 FastAPI。
- `run-dev.ps1` / `run-dev.sh`：开发模式启动 FastAPI，并启用 uvicorn 热重载。

验证、迁移、临时排查脚本不放在本目录，避免把一次性工具当成项目入口提交。
