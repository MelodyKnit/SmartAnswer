# 本地发布更新器

`update-from-github.sh` 在部署服务器本地运行，定期读取配置的 GitHub Release，校验
`release-manifest.json` 后拉取不可变镜像，并调用 `apply-release.sh` 完成本地 Compose
切换。它不向 GitHub 发起 SSH 连接，也不需要服务器把 IP、SSH 私钥或主机指纹配置到
GitHub 仓库。

## 配置

复制 `update.env.example` 到服务器的私有配置路径，至少填写：

- `STQB_PROJECT_DIR`：服务器上现有 Compose 项目目录。
- `STQB_SOURCE_REPOSITORY`：要跟随的 GitHub 仓库。
- `STQB_HEALTH_URL`：容器映射到宿主机的本地健康检查地址，例如
  `http://127.0.0.1:3003`。
- `STQB_DOCKER_CONTEXT`：默认使用 `rootless`；必须与运行服务用户执行 `docker context show`
  的结果一致。
- `STQB_ALLOW_SOURCE_FALLBACK`：默认启用。GHCR 镜像不可读时，从 manifest 指定的 Release
  commit 下载源码并在本机带版本元数据构建；可设为 `false` 强制只使用镜像。
- `STQB_RELEASE_BACKUP_KEEP`：保留的 SQLite 发布快照数，默认 `2`，范围 `1-100`。更新器在每次检查时以及拉取候选镜像前清理更旧的、命名格式正确的发布快照。
- `STQB_RELEASE_IMAGE_KEEP`：保留的本项目镜像数，默认 `2`，范围 `2-20`。当前运行镜像始终保留，至少另留一个回滚镜像；更新器仅清理本项目 GHCR 镜像和本地回退镜像的多余引用。

公开仓库和公开 GHCR 镜像不需要凭据。GHCR 不可读时默认使用经过 manifest 校验的源码
构建回退。私有仓库使用 `STQB_GITHUB_TOKEN_FILE`，私有
GHCR 镜像使用 `STQB_GHCR_USERNAME` 与 `STQB_GHCR_TOKEN_FILE`。凭据文件只保存在
服务器，权限应为 `600`。

升级后，模型接口地址、模型名和 API 密钥只从部署数据库读取。若旧实例仅通过 `STQB_LLM_*` 环境变量配置模型，需先在后台「大模型配置」创建并测试 active 模型，再移除旧变量；旧环境变量不会自动导入数据库。

## 启动方式

手动检查或更新：

```bash
bash /srv/study-qb-assistant/deploy/update-from-github.sh \
  /etc/study-qb-assistant/update.env
```

只执行存储清理、不检查 GitHub Release：

```bash
bash /srv/study-qb-assistant/deploy/update-from-github.sh \
  --cleanup-only /etc/study-qb-assistant/update.env
```

先查看将清理的快照和镜像引用，可将 `--cleanup-only` 换为 `--cleanup-preview`；预览不会删除文件或镜像。

清理操作只处理 `${STQB_PROJECT_DIR}/deploy-data/backups/releases/` 下符合时间戳和版本号格式的直接子目录，并保留最近配置数量；其他目录、文件及符号链接不会递归删除。Docker 清理只针对当前项目镜像引用，保留运行中镜像和最近镜像；被其他容器占用的镜像会由 Docker 拒绝删除并记录跳过。

兼容旧快照的 `vX.Y.Z` 与 `-manual` 后缀。没有非空数据库文件或标记为 `.incomplete` 的目录不会挤占正常回滚名额，也不会自动删除。成功部署后，`.env.release.previous` 和 `deploy/docker-compose.previous.yaml` 保存上一个成功版本；镜像清理同时保护该版本、当前版本、所有容器引用和带有其他项目标签的镜像。清理仅在宿主机执行，应用容器不需要 Docker socket 权限。

自动更新可使用用户级 systemd timer。将 `systemd/` 下两个单元复制到
`~/.config/systemd/user/`，按实际项目路径修改 service 的 `ExecStart`，然后执行：

```bash
systemctl --user daemon-reload
systemctl --user enable --now stqb-release-update.timer
systemctl --user start stqb-release-update.service
systemctl --user status stqb-release-update.timer
```

服务器只会跟随已发布的正式 `vX.Y.Z` Release；普通分支 push 不会直接部署。Release
发布后，下一次轮询会自动执行。版本比较、镜像 digest 校验、SQLite 备份、健康检查和
失败回滚仍由本地 `apply-release.sh` 负责。

OCS Compose 服务默认带有内存、CPU、进程数和 JSON 日志轮转保护。应用层的查题并发/速率限制仍在系统配置中控制；两层保护同时生效，容器资源上限用于避免单个 OCS 实例拖垮同机其他服务。
