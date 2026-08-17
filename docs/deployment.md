# Server Deployment

生产环境使用公开 GHCR 的不可变镜像，通过 GitHub Actions 的 `production`
Environment 部署。业务容器不执行 `git pull`、不访问 Docker Socket，也不保存 GitHub
Token。

## 部署边界

- `Dockerfile`：构建 Python 运行时和前端静态资源。
- `docker-compose.yaml`：仅接受 `STQB_IMAGE_REF` 指向的镜像 digest，拒绝可变标签启动。
- `.env.server`：服务器本地业务配置，未提交到仓库。
- `.env.release`：由发布工作流的远端脚本原子生成，记录当前镜像 digest、版本和提交号。
- `docker-compose.override.yml`：服务器本地运维覆盖层，例如 rootless 端口映射、外部网络和 NewAPI 连接；发布不会覆盖它。
- `deploy/docker-compose.release-image.yaml`：发布脚本生成的最终镜像覆盖层，确保本地覆盖文件不能把候选 digest 覆盖回旧镜像。
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

生产实例应使用部署账户的 rootless Docker。发布工作流通过该账户 SSH
登录，直接在同一个 rootless Docker context 中原子安装发布资产并运行发布脚本；业务容器本身不持有
Docker Socket 或 GitHub 凭据。不要通过 `sudo` 发布，否则会切换到 root Docker context：

```bash
install -d -m 0755 "$DEPLOY_PATH/deploy"
install -d -m 0775 "$DEPLOY_PATH/deploy-data"
```

当前工作流会先将候选 Compose 和发布脚本上传到该账户的
`~/.cache/stqb-release.*`，校验后再以该账户权限安装到项目目录。目标 Docker context
必须是 `rootless`，否则发布脚本会在开始前失败，避免误操作 root Docker。

线上 `docker-compose.override.yml` 是服务器专用文件，必须保留在项目目录中。它可以覆盖端口、网络和本地依赖服务；发布脚本会额外生成一个最后加载的镜像覆盖文件，使 Release manifest 中的不可变 digest 始终成为实际运行镜像。

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
3. 添加 Variables：`DEPLOY_HOST`、`DEPLOY_PORT`、`DEPLOY_USER`、`DEPLOY_PATH`、`DEPLOY_HEALTH_URL`、`DEPLOY_DOCKER_CONTEXT`。
4. 将 GHCR 包设为公开。GitHub 新建包通常默认私有；首次镜像发布后，应在 Packages 页面调整为 Public，再批准部署任务。

生产实例的变量应指向部署账户的 rootless Docker 服务：端口使用 SSH 实际端口，项目路径使用 `DEPLOY_PATH`，健康检查地址使用该实例 Compose 覆盖层暴露的本机地址，Docker context 为 `rootless`。`DEPLOY_HOST` 和 SSH 私钥只保存在 GitHub Environment，不写入仓库。这些值不会写入数据库、`.env.server` 或业务容器。

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

健康检查或启动失败时，脚本会恢复上一份 Compose、`.env.release`、最终镜像覆盖和 SQLite 快照。对于已运行但尚未纳入受控发布的旧容器，脚本会读取其镜像与构建信息作为一次性回滚目标，避免首次迁移失败时误删线上服务。脚本会
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

服务监听容器端口 `8765`。由服务器专用 `docker-compose.override.yml` 决定宿主机监听地址与端口，反向代理再将公开域名转发到该地址。反向代理需要正确传递 `Host` 和 `X-Forwarded-Proto`，以便生成可访问的 OCS 图片 URL。
