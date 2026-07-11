# 私有仓库主机更新器

主机更新器负责 GitHub Release 检测、私有 GHCR 镜像拉取、SQLite 备份、
Compose 切换、健康检查和失败自动回滚。业务容器不持有 GitHub Token，
也不挂载 Docker Socket。

## 安装

```bash
sudo ./deploy/updater/install.sh
sudo editor /etc/stqb-updater.env
sudo systemctl start stqb-updater-check.service
```

需要两个最小权限凭据：

- `STQB_UPDATE_GITHUB_TOKEN`：细粒度 PAT，只授权当前私有仓库的 Contents/Metadata 只读。
- `STQB_UPDATE_GHCR_TOKEN`：classic PAT，仅 `read:packages`。

真实凭据只保存在 `/etc/stqb-updater.env`，文件权限必须为 `0600`。

## 运行边界

- `stqb-updater.path` 监听 `deploy-data/update/requests/*.json`。
- `stqb-updater-check.timer` 每 6 小时检查一次正式 Release。
- 更新只接受 `release-manifest.json` 声明的固定仓库、固定 GHCR 镜像和 digest。
- 更新前使用 SQLite 在线备份 API 创建一致性快照。
- 健康检查或版本检查失败时自动恢复上一镜像和数据库。
- 只清理本项目历史镜像引用，不执行全局 Docker 清理。

查看状态：

```bash
systemctl status stqb-updater.path stqb-updater-check.timer
journalctl -u stqb-updater.service -u stqb-updater-check.service -f
```
