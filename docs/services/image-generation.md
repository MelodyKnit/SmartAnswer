# 文本生图服务

更新时间：`2026-07-25`

## 目标与边界

文本生图是一个独立的用户能力，不复用聊天模型、查题使用记录或 OCS 图片图床。首版只支持
单张文本生图和受控的图片协议提供商；不支持图生图、批量生成、
公开分享或通过 OCS/API Key 调用。

实现边界：

- `llm/image_generation/`：供应商契约、Gemini 原生、OpenAI Images、通用兼容 Images 与旧聊天生图协议适配器。
- `platform/image_generation/`：模型配置、任务状态、积分结算、恢复和清理编排。
- `storage/repositories/image_generation.py`：模型、任务、资产、追溯和积分预扣事务。
- `media/generated_images.py`：图片内容校验、私有文件存储和删除。
- `api/v1/image_generation/`：用户与管理员 API 边界。

## 任务与积分生命周期

```text
创建任务 -> queued -> running -> succeeded
                  |          |
                  +-> cancelled
                             +-> failed / rejected
```

1. 创建任务时，在同一数据库事务内校验用户余额、活动任务数与每日限额，写入任务和积分预扣订单。
2. 工作器以原子领取方式将 `queued` 任务改为 `running`，然后只调用一次选定供应商。
3. 成功图片经过 MIME、体积、像素和解码校验，并保存至少一个私有资产后，预扣订单标记为完成。
4. 供应商拒绝、超时、下载失败、非法图片或本地写入失败时，任务标记为失败并只退款一次。
5. 应用启动时会回收过期的 `running` 任务并退款；不会自动把它们再次提交给供应商。

同一用户默认只能有一个 `queued` 或 `running` 任务。客户端可显式提供 `Idempotency-Key`，重复
提交会返回原任务而不是再次扣费。用户可以取消仍在排队的任务；运行中的任务不能盲目取消，
避免供应商已接收请求时产生重复成本。

## 模型与密钥

管理员在“大模型配置 > 生图模型”中维护模型。模型保存提供商、Base URL、模型标识、超时和受控
`protocol_config`；API Key 只能写入，读取接口只返回是否已配置。启用新模型会停用旧模型，后续新任务
只使用当前启用模型。

`gemini-native` 使用 `POST /models/{model}:generateContent`，按配置使用 `x-goog-api-key` 或 Bearer
鉴权，并传递 `imageConfig.aspectRatio` 与 `imageConfig.imageSize`；它从 `inlineData` 读取图片。
`openai-images` 使用 `/images/generations`，可使用预设尺寸，或在管理员明确声明约束后使用自定义尺寸。
`openai-compatible-images` 同样调用 `/images/generations`，但只允许管理员声明的预设尺寸。旧
`openai-chat-image` 使用 `/chat/completions`，从返回的 Markdown/data URL 或内容块中读取图片，尺寸由
上游模型决定，不推荐用于新配置。

任务创建时保存非敏感模型参数与归一化输出参数快照，任务响应中的 `size` 显示请求的输出选择，
`assets[].width/height` 显示实际输出尺寸。后台执行仍从受控模型记录读取当前 API Key，因此密钥不会
复制到任务快照、调用追溯、日志或 API 响应。管理员之后切换模型或修改模型地址不会把已排队任务
隐式切换到另一套提供商参数。

## 资产、隐私与保留期

输出保存在 `data/images/generations/`，文件仅使用随机资产键，不保存到 Git。图片内容经过
Pillow 解码验证，允许 JPEG、PNG、WebP，单张最大 10 MB，像素数受限。供应商若返回临时 URL，
服务端立即安全下载并保存，不将该 URL 返回给前端。

前端用 JWT 请求私有内容接口，再在浏览器内创建临时 Blob 预览 URL。资产接口只允许任务所有者
或管理员访问，并返回 `Cache-Control: private, no-store`。默认保留 30 天，系统配置可改为
`0`（永久保留）；清理任务会先撤销数据库资产访问，再删除未引用文件。

## 调用追溯与排障

`image_generation_traces` 仅记录任务、模型、提供商阶段、耗时、供应商请求标识和经过脱敏的
错误分类。它不会记录提示词、原始供应商响应、图片字节、Base64、第三方 URL 或 API Key。

常见错误码：

- `IMAGE_GENERATION_UNAVAILABLE`：没有启用的生图模型。
- `INSUFFICIENT_POINTS`：余额不足。
- `IMAGE_GENERATION_CONCURRENCY_LIMIT`：用户仍有活动任务。
- `IMAGE_GENERATION_DAILY_LIMIT`：已达到每日上限。
- `CONTENT_POLICY_REJECTED`：供应商内容策略拒绝，请求未确认扣费。
- `PROVIDER_TIMEOUT`、`PROVIDER_UNAVAILABLE`：供应商不可用，任务失败并退款。
- `WORKER_INTERRUPTED`：应用重启回收的遗留运行任务，已退款。
