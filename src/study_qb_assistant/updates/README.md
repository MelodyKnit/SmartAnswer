# 在线更新应用边界

`ProjectUpdateService` 是业务容器与主机更新器之间的最小命令网关。

- 应用只在 `STQB_DATA_DIR/update/` 写入结构化 JSON 命令并读取状态。
- GitHub 凭据、GHCR 凭据和 Docker 权限只属于宿主机更新器。
- `check` 与 `apply` 均为异步操作，调用方通过操作 ID 轮询状态。
- `apply` 只允许提交最近一次检查得到的稳定版本，主机更新器还会再次校验。

状态目录：

```text
update/
  status.json
  requests/<operation_id>.json
  operations/<operation_id>.json
```

主机执行器与部署说明位于 `deploy/updater/README.md`。
