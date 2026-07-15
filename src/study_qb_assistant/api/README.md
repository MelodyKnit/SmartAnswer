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
- `middleware.py`：CORS、SPA 和旧接口弃用响应头。
- `query_execution.py`：查题调用、计费和使用记录编排。
- `legacy.py`：旧无前缀业务路径的临时兼容规则。

## 路由规则

- 规范业务接口统一使用 `/api/v1/...`。
- `/ocs/query` 是唯一保留的无版本业务入口。
- 旧无前缀路径复用同一份 v1 router，不复制实现，不进入 OpenAPI，并返回 `Deprecation` 与 successor `Link`。
- OpenAPI 位于 `/api/v1/openapi.json`，文档位于 `/api/docs`。
- 路由只处理 HTTP 边界、鉴权、错误映射和响应组装；业务规则放入领域服务。
