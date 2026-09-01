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

公开仓库和公开 GHCR 镜像不需要凭据。私有仓库使用 `STQB_GITHUB_TOKEN_FILE`，私有
GHCR 镜像使用 `STQB_GHCR_USERNAME` 与 `STQB_GHCR_TOKEN_FILE`。凭据文件只保存在
服务器，权限应为 `600`。

## 启动方式

手动检查或更新：

```bash
bash /srv/study-qb-assistant/deploy/update-from-github.sh \
  /etc/study-qb-assistant/update.env
```

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
