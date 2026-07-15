# OCS 风格适配器

更新时间：`2026-06-07`

## 1. 目的

本地服务暴露了 `/ocs/query` 作为围绕稳定内部 `/query` API 的薄兼容性端点。

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

- [configs/ocs-local-study-bank.json](../configs/ocs-local-study-bank.json)

本地服务运行时，相同的源配置也会在以下地址提供：

```text
http://127.0.0.1:8765/api/v1/configs/ocs-local-study-bank.json
```

为自定义主机或端口生成配置：

```powershell
手动修改 [configs/ocs-local-study-bank.json](../configs/ocs-local-study-bank.json) 中的 base URL
```

配置内容：

```json
[
  {
    "name": "Local Study Question Bank",
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

OCS/Tampermonkey 部署可能还需要脚本环境允许连接 to 本地主机，例如 `127.0.0.1` 或 `localhost`。项目服务会发送宽松的 CORS 标头，但用户脚本管理器仍可能强制执行其自己的连接白名单。

## 4. 成功响应结构

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "question": "壁胸膜的分部不包括",
    "answer": "B",
    "answer_text": "肺胸膜",
    "explanation": null,
    "ai": {
      "review_required": false,
      "confidence": 0.99,
      "resolution_mode": "exact_match",
      "sources": []
    }
  }
}
```

## 5. 错误响应结构

```json
{
  "code": 1,
  "message": "title is required",
  "data": {
    "question": "",
    "answer": null,
    "ai": {
      "review_required": true,
      "confidence": 0.0,
      "resolution_mode": "invalid_request",
      "error_code": "INVALID_REQUEST"
    }
  }
}
```

## 6. 审核边界

适配器在 `data.ai` 中保留了 `review_required`、`confidence`、`resolution_mode` 和 `sources`。外部客户端应尽可能使这些元数据保持可见，尤其是对于模糊匹配或仅由模型生成的结果。

## 7. 验证

当前建议的验证方式：

- 直接请求运行中的 `/ocs/query`
- 检查返回的 `code/data/ai` 结构
- 在真实 OCS 页面中验证 handler 是否能消费返回的 `answer`

## 8. 客户端桥接脚本

如果 OCS 官方脚本在某些定制学习平台上无法识别题目，可以使用仓库内的本地客户端脚本：

- [client-scripts/sisu-ocs-client-bridge.user.js](../../client-scripts/sisu-ocs-client-bridge.user.js)

该脚本通过 OCS 桌面端“添加本地脚本”加载，运行后会在目标学习页面右下角显示手动操作面板。它会从当前可见题目区域提取题干、选项和题型，调用本项目 `/ocs/query`，然后把答案回填到当前页面控件。

边界说明：

- 该脚本不修改 OCS 源码，也不依赖 OCS 的平台项目适配。
- 该脚本只回填当前页面可见题目，不点击平台提交按钮。
- 服务地址和 API Key 在页面面板中配置，真实密钥不应写入仓库文件。
