# 部署指南

生产环境使用“GitHub Release + 服务器本地更新器”发布。GitHub 只构建、签名版本信息并发布不可变镜像；每台服务器主动验证 Release 后在本机切换容器。服务器地址、SSH 密钥和部署凭据不会写入仓库或 GitHub Actions。

## 1. 发布流程

1. 本地完成验证后更新 `pyproject.toml` 版本，提交并创建匹配的 `vX.Y.Z` tag。
2. 推送 tag 后，GitHub Actions 构建镜像并发布带有 `release-manifest.json` 的正式 GitHub Release。
3. 服务器上的 `deploy/update-from-github.sh` 读取最新正式 Release，校验仓库、tag、版本、提交号、镜像 digest 和平台。
4. `deploy/apply-release.sh` 备份 SQLite 数据库，切换 Docker Compose 服务，并验证 `/api/v1/healthz` 与 `/api/v1/version`；失败时自动回滚上一个可用版本。

普通分支 push 不会部署。只有正式 `vX.Y.Z` Release 会被服务器更新器采用。

## 2. 首次部署

部署主机需要 Docker、Docker Compose、`curl`、`python3`、`tar` 和 `flock`。先创建项目目录并放置当前仓库的 `deploy/` 目录，例如：

```bash
git clone https://github.com/MelodyKnit/SmartAnswer.git /srv/study-qb-assistant
cp /srv/study-qb-assistant/deploy/update.env.example /etc/study-qb-assistant/update.env
chmod 600 /etc/study-qb-assistant/update.env
```

编辑私有 `update.env`：

- `STQB_PROJECT_DIR`：部署目录，例如 `/srv/study-qb-assistant`。
- `STQB_HEALTH_URL`：宿主机健康检查地址，例如 `http://127.0.0.1:3003`。
- `STQB_DOCKER_CONTEXT`：部署用户执行 `docker context show` 的输出。
- 私有仓库或私有 GHCR 镜像时，使用本机权限为 `600` 的凭据文件配置 `STQB_GITHUB_TOKEN_FILE` 或 `STQB_GHCR_TOKEN_FILE`。

运行首个正式 Release：

```bash
bash /srv/study-qb-assistant/deploy/update-from-github.sh /etc/study-qb-assistant/update.env
```

运行数据保存在 `${STQB_PROJECT_DIR}/deploy-data/`：SQLite、日志、用户配置和私有图片资产都在此目录中，镜像更新不会覆盖它。

## 3. 自动更新与检查

可按 [deploy/README.md](../../deploy/README.md) 配置用户级 systemd timer，使服务器定期检查正式 Release。手动检查或更新仍使用同一命令：

```bash
bash /srv/study-qb-assistant/deploy/update-from-github.sh /etc/study-qb-assistant/update.env
```

查看当前服务与日志：

```bash
cd /srv/study-qb-assistant
docker compose --env-file .env.release -f docker-compose.yaml ps
docker compose --env-file .env.release -f docker-compose.yaml logs -f --tail=100
curl --fail http://127.0.0.1:3003/api/v1/healthz
curl --fail http://127.0.0.1:3003/api/v1/version
```

不要在受更新器管理的生产目录中执行 `docker compose up -d --build`。这会绕过 Release manifest 校验、数据库备份和自动回滚。
