# OCS 风格适配器

更新时间：`2026-06-07`

## 1. 目的

本地服务暴露了 `/ocs/query` 作为围绕稳定内部查询 API 的薄兼容性端点。路径、请求、响应和错误契约统一维护于[查询与诊断 API](../architecture/apis/query.md)。

在外部客户端期望紧凑的 `code/data` 响应形式的本地学习和复习工作流中使用它。

## 2. 端点

```text
http://127.0.0.1:8765/ocs/query
```

支持的方法：

- `GET`
- `POST`

## 3. 配置产物

本地配置文件：

- [configs/ocs-local-study-bank.json](../../configs/ocs-local-study-bank.json)

本地服务运行时，相同的源配置也会在以下地址提供：

```text
http://127.0.0.1:8765/api/v1/configs/ocs-local-study-bank.json
```

为自定义主机或端口生成配置：

```powershell
手动修改 [configs/ocs-local-study-bank.json](../../configs/ocs-local-study-bank.json) 中的 base URL
```

配置内容：

```json
[
  {
    "name": "当前平台名称",
    "homepage": "http://127.0.0.1:8765/api/v1/healthz",
    "url": "http://127.0.0.1:8765/ocs/query",
    "method": "get",
    "type": "GM_xmlhttpRequest",
    "contentType": "json",
    "data": {
      "title": "${title}",
      "options": "${options}",
      "type": "${type}"
    },
    "handler": "return (res)=>res.code === 0 ? [res.data.question, res.data.answer] : [res.message || (res.data && res.data.question) || '未找到答案', undefined]"
  }
]
```

OCS 期望 handler 的返回值将答案放在第二个位置。因此，本地配置在请求成功时返回 `[question, answer]`。

运行时配置接口会读取系统 `site_title` 作为题库名称；经 API Key 页面复制时，会追加该 Key 的名称，格式为 `平台名称 · API Key 名称`。名称为空时只追加掩码末尾四位，避免泄露密钥。

OCS 部署可能需要允许其请求运行该服务的主机，例如 `127.0.0.1` 或 `localhost`。项目服务会发送 CORS 标头；实际访问限制也可能由 OCS 宿主环境控制。

## 4. 审核边界

适配器在 `data.ai` 中保留了 `review_required`、`confidence`、`resolution_mode` 和 `sources`。外部客户端应尽可能使这些元数据保持可见，尤其是对于模糊匹配或仅由模型生成的结果。

## 5. 验证

当前建议的验证方式：

- 直接请求运行中的 `/ocs/query`
- 检查返回的 `code/data/ai` 结构
- 在真实 OCS 页面中验证 handler 是否能消费返回的 `answer`
