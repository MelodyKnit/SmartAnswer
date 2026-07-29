# Server Deployment

生产环境使用公开 GHCR 的不可变镜像，通过 GitHub Actions 的 `production`
Environment 部署。业务容器不执行 `git pull`、不访问 Docker Socket，也不保存 GitHub
Token。

## 部署边界

- `Dockerfile`：构建 Python 运行时和前端静态资源。
- `docker-compose.yaml`：仅接受 `STQB_IMAGE_REF` 指向的镜像 digest，拒绝可变标签启动。
- `.env.server`：服务器本地业务配置，未提交到仓库。
- `.env.release`：由发布工作流的远端脚本原子生成，记录当前镜像 digest、版本和提交号。
- `deploy/remote-release.sh`：GitHub Actions 通过 SSH 临时执行，负责备份、切换、健康检查和回滚。

镜像只包含代码、构建后的前端和提交的默认配置，不包含 `.env`、题库、SQLite、日志或图片数据。

## 运行数据

所有可变数据都保存在服务器的 `deploy-data/`：

- `deploy-data/runtime/`：SQLite 和运行时状态。
- `deploy-data/logs/`：应用日志。
- `deploy-data/normalized/`：导入后的题库数据。
- `deploy-data/images/ocs/`：OCS 图片题资产。
- `deploy-data/images/generations/`：文本生图资产。
- `deploy-data/images/generation-inputs/`：用户私有上传的参考图与蒙版资产。
- `deploy-data/backups/releases/`：发布前的 SQLite 一致性快照。

容器内使用 `/app/data`，由 Compose 映射到该目录。更新镜像不会覆盖运行数据。

## 服务器准备

在服务器上创建部署目录与可持久化数据目录。发布工作流通过部署账户 SSH
登录，并使用无密码 `sudo` 原子安装发布资产、运行受控发布脚本；业务容器本身不持有
Docker Socket 或 GitHub 凭据：

```bash
sudo install -d -o root -g root -m 0755 /opt/study-question-bank-assistant/deploy
sudo install -d -o "$USER" -g "$USER" -m 0775 /opt/study-question-bank-assistant/deploy-data
# 仅对实际部署账户配置；执行前请确认 sudoers 规则符合本机安全基线。
sudo visudo
```

部署账户必须能在不交互输入密码的情况下执行 `sudo -n install` 与
`sudo -n bash /opt/study-question-bank-assistant/deploy/remote-release.sh`。当前工作流会先将
候选 Compose 和发布脚本上传到该账户的 `~/.cache/stqb-release.*`，校验后再以 root 权限
安装到项目目录；它不会直接向 root 所有目录执行 SCP。

可选地创建 `.env.server` 保存模型、代理等业务配置。该文件与发布版本无关，示例见
`.env.server.example`。常用配置包括：

- `STQB_LLM_BASE_URL`
- `STQB_LLM_MODEL`
- `STQB_LLM_API_KEY`
- `STQB_REQUIRE_AUTH=true`
- `STQB_PUBLIC_BASE_URL=https://your-public-domain`
- `STQB_REDIS_URL`（仅共享会话需要时）

模型网关或代理运行在宿主机时，容器内应通过 `host.docker.internal` 访问，不要使用
`127.0.0.1`。视觉模型要读取 OCS 图片时，`STQB_PUBLIC_BASE_URL` 必须是模型可访问的
HTTPS 地址。

## GitHub Environment

在 GitHub 仓库中创建名为 `production` 的 Environment，并配置部署保护规则：

1. 启用必需审批人，并限制为维护者可以发布的版本标签。
2. 添加 Secrets：`DEPLOY_SSH_PRIVATE_KEY`、`DEPLOY_KNOWN_HOSTS`。
3. 添加 Variables：`DEPLOY_HOST`、`DEPLOY_PORT`、`DEPLOY_USER`、`DEPLOY_PATH`、`DEPLOY_HEALTH_URL`。
4. 将 GHCR 包设为公开。GitHub 新建包通常默认私有；首次镜像发布后，应在 Packages 页面调整为 Public，再批准部署任务。

`DEPLOY_HEALTH_URL` 应是服务器本机的服务地址，例如 `http://127.0.0.1:3003`。这些值只存在于 GitHub Environment；不会写入数据库、`.env.server` 或业务容器。

## 首次发布

首次不需要手工创建 `.env.release`，也不需要在服务器执行 `docker login`。完成 GitHub
Environment 配置后，按以下方式发布：

```bash
# 在本地完成验证后
git add .
git commit -m "release: vX.Y.Z"
git tag vX.Y.Z
git push origin HEAD --tags
```

`release.yml` 会按顺序执行：

1. 校验 `vX.Y.Z` 与 `pyproject.toml` 版本和标签提交一致。
2. 运行后端测试、前端构建和发布脚本语法检查。
3. 构建并发布 `linux/amd64` GHCR 镜像，以及 `release-manifest.json`。
4. 创建正式 GitHub Release。
5. 等待 `production` Environment 审批。
6. 远端脚本匿名拉取 manifest 中的精确 digest，备份 SQLite，原子切换 Compose，并验证 `/api/v1/healthz` 与 `/api/v1/version`。

健康检查或启动失败时，脚本会恢复上一份 Compose、`.env.release` 和 SQLite 快照。脚本会
从运行中容器读取实际 SQLite 路径，且只接受 `/app/data` 挂载内的数据库；使用外部数据库
时不会创建 SQLite 快照，需要由外部数据库自身负责备份和回滚。首次发布没有旧版本时会清理候选配置并失败退出，不会把失败镜像标记为当前版本。

## 重新部署已发布版本

如需重新部署某个已发布版本，在 GitHub Actions 手工运行 `Deploy Existing Release`，输入
`vX.Y.Z`。工作流会下载并校验该 Release 的 `release-manifest.json`，再走同一套
备份、digest 切换、健康检查和回滚逻辑。不要在服务器上按 `stable` 标签手工更新。

## 应用内状态页

**系统配置 > 版本发布** 只显示当前构建和最近一次公开 GitHub Release 检查结果。它不会保存 GitHub Token、触发 GitHub Actions 或修改生产容器。正式部署始终从 GitHub 的受保护 Environment 发起。

应用启动时会删除旧版本遗留的 `project_update_*` 系统配置，包括旧的 GitHub Token，避免迁移后继续在 SQLite 中保留不再使用的部署凭据。

## 反向代理

服务监听容器端口 `8765`、宿主机端口 `3003`。Nginx 可将公开域名转发到
`http://127.0.0.1:3003`。反向代理需要正确传递 `Host` 和 `X-Forwarded-Proto`，以便生成可访问的 OCS 图片 URL。
