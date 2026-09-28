# API 结构

`api/app.py` 只负责创建 FastAPI 应用和挂载路由。业务接口按版本和领域组织。

## 入口

- `app.py`：应用组装与运行时状态挂载。
- `v1/router.py`：`/api/v1` 唯一聚合入口。
- `v1/<domain>/router.py`：领域路由。
- `v1/<domain>/schemas.py`：该领域的请求模型。
- `ocs/router.py`：稳定公共入口 `/ocs/query`。
- `static/router.py`：前端静态资源和 SPA 页面。

## 公共能力

- `dependencies.py`：按领域读取运行时服务。
- `security.py`：身份、角色与权限校验。
- `middleware.py`：CORS 和 SPA 回退。
- `query_execution.py`：查题调用、计费和使用记录编排。
- `query_admission.py`：按用户和全局活动数执行查题速率/并发准入，超限快速返回 `429`。

查题准入配置由系统配置提供，但控制器保留代码级安全上限；当前单实例部署使用进程内线程安全计数，多副本部署时需要替换为共享限流存储。

## 路由规则

- 规范业务接口统一使用 `/api/v1/...`。
- `/ocs/query` 是独立的 OCS 公共适配入口，不进入版本化业务路由。
- OpenAPI 位于 `/api/v1/openapi.json`，文档位于 `/api/docs`。
- 路由只处理 HTTP 边界、鉴权、错误映射和响应组装；业务规则放入领域服务。
