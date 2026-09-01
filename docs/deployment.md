# Server Deployment

生产部署采用“GitHub 发布、服务器主动拉取”的模式。GitHub Actions 只负责运行测试、
构建并发布 GHCR 不可变镜像和 `release-manifest.json`；每台服务器由自己的本地更新器
定期读取 GitHub Release，在本机完成镜像切换。GitHub 不保存服务器 IP、SSH 私钥或主机
指纹，也不需要 `production` Environment 审批。

## 部署边界

- `Dockerfile`：构建 Python 运行时和前端静态资源。
- `docker-compose.yaml`：只接受 `STQB_IMAGE_REF` 指向的镜像 digest，拒绝可变标签启动。
- `.env.server`：服务器本地业务配置，未提交到仓库。
- `.env.release`：本地更新器生成，记录当前镜像 digest、版本和提交号。
- `docker-compose.override.yml`：服务器本地运维覆盖层，更新器不会覆盖。
- `deploy/update-from-github.sh`：服务器本地 Release 检查与更新入口。
- `deploy/apply-release.sh`：本地 Compose 切换、数据备份、健康检查和自动回滚。

镜像只包含代码、构建后的前端和提交的默认配置，不包含 `.env`、题库、SQLite、日志或
图片数据。

## 运行数据

所有可变数据都保存在服务器的 `deploy-data/`：

- `deploy-data/runtime/`：SQLite 和运行时状态。
- `deploy-data/logs/`：应用日志。
- `deploy-data/normalized/`：导入后的题库数据。
- `deploy-data/images/ocs/`：OCS 图片题资产。
- `deploy-data/images/generations/`：生图资产。
- `deploy-data/images/generation-inputs/`：用户私有参考图与蒙版资产。
- `deploy-data/backups/releases/`：发布前的 SQLite 一致性快照。

容器内使用 `/app/data`，由 Compose 映射到该目录。更新镜像不会覆盖运行数据。

## 首次安装

服务器只需准备一次 Docker、`bash`、`curl`、`python3` 和 `flock`。部署账户应能访问与
业务容器相同的 `rootless` Docker context，不需要把 Docker Socket 暴露给业务容器。

把项目的 Compose 和更新脚本放到服务器项目目录，并创建本地配置：

```bash
install -d -m 0755 /srv/study-qb-assistant/deploy
install -d -m 0775 /srv/study-qb-assistant/deploy-data
install -d -m 0700 /etc/study-qb-assistant
cp deploy/update.env.example /etc/study-qb-assistant/update.env
chmod 600 /etc/study-qb-assistant/update.env
```

编辑 `update.env`，至少填写：

```dotenv
STQB_PROJECT_DIR=/srv/study-qb-assistant
STQB_SOURCE_REPOSITORY=MelodyKnit/SmartAnswer
STQB_HEALTH_URL=http://127.0.0.1:3003
STQB_DOCKER_CONTEXT=rootless
STQB_PLATFORM=linux/amd64
STQB_ALLOW_DOWNGRADE=false
```

`STQB_HEALTH_URL` 必须是服务器本机地址，不是公网域名；应填写运行用户实际可访问的
宿主机映射端口，例如 `http://127.0.0.1:13003`。仓库和 GHCR 都公开时无需任何
凭据。私有仓库使用服务器本地的 `STQB_GITHUB_TOKEN_FILE`；私有 GHCR 使用
`STQB_GHCR_USERNAME` 和 `STQB_GHCR_TOKEN_FILE`。凭据文件权限应为 `600`，不写入项目、
GitHub Actions 或容器环境。

现有通过 GitHub SSH 发布的服务器迁移时，只需保留原 `deploy-data/`、`.env.server` 和
本地运维覆盖层，重新安装 `update-from-github.sh` 与本地配置即可；更新器会从首个
新 Release 下载 `apply-release.sh`。如果希望提前准备，也可以同时复制这两个脚本。
不要删除现有数据库，也不要在服务器执行 `git reset`。首次拉取成功前，旧容器不会被
更新器主动停止。

## 自动更新

更新器只跟随正式发布的 `vX.Y.Z` GitHub Release，不直接读取普通分支。GitHub Release
发布后，下一次轮询会自动执行：

```text
读取 Release metadata
  -> 下载并校验 release-manifest.json
  -> 按 manifest 提交号读取 Compose 与部署脚本
  -> 校验镜像仓库、版本、commit SHA、平台和 digest
  -> 本地拉取镜像并切换 Compose
  -> 健康检查 /api/v1/healthz 与 /api/v1/version
  -> 失败恢复旧 Compose、镜像配置和 SQLite 快照
```

用户级 systemd timer 示例：

```bash
mkdir -p ~/.config/systemd/user
cp deploy/systemd/stqb-release-update.service ~/.config/systemd/user/
cp deploy/systemd/stqb-release-update.timer ~/.config/systemd/user/
# 按实际项目路径修改 service 的 ExecStart
systemctl --user daemon-reload
systemctl --user enable --now stqb-release-update.timer
systemctl --user start stqb-release-update.service
systemctl --user status stqb-release-update.timer
```

也可以手动运行：

```bash
bash /srv/study-qb-assistant/deploy/update-from-github.sh \
  /etc/study-qb-assistant/update.env
```

同一个仓库可以被多台服务器分别跟随。每台服务器只读取自己的本地配置，更新失败只
影响当前服务器，不会影响其他实例。

确认至少一台服务器已手动成功运行更新器并能正常回滚后，可在 GitHub 仓库的 Settings
中删除旧的 `production` Environment 及其中的 `DEPLOY_*` 变量和 Secrets。新工作流不再
读取这些配置；迁移前不要提前删除，以免旧版本仍需要回滚。

## 发布版本

本地完成检查后，创建正式版本标签并推送：

```bash
git add .
git commit -m "release: vX.Y.Z"
git tag vX.Y.Z
git push origin HEAD --tags
```

`release.yml` 会校验版本、执行后端测试和前端构建，推送 `linux/amd64` GHCR 镜像并创建
Release manifest。它不使用服务器地址、SSH 密钥或 GitHub Environment，发布完成后由
各服务器的本地 timer 自行获取更新。

服务器不会按 `stable` 或其他可变标签更新，而是始终使用 manifest 中的 digest。发布
版本相同但 digest 不同会被拒绝，避免覆盖不可变发布。

## 应用内版本状态

**系统配置 > 版本发布** 只负责查询公开 GitHub Release 并展示版本关系：

- `GET /api/v1/project-update/status`：读取最近一次检查缓存。
- `POST /api/v1/project-update/check`：由网站主动查询 GitHub Release。

应用内检查不会触发部署。服务器本地更新器与应用本身解耦，应用停止或升级时仍由宿主机
timer 负责执行更新。

## 反向代理

服务监听容器端口 `8765`。服务器专用 `docker-compose.override.yml` 决定宿主机监听地址
与端口，反向代理再将公开域名转发到该地址。反向代理需要正确传递 `Host` 和
`X-Forwarded-Proto`，以便生成可访问的 OCS 图片 URL。
