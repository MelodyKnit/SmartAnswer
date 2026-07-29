# 图片生成提供商适配

本包定义独立于查题聊天模型的生图与修图契约，并提供三种正式调用协议与一个旧版兼容协议。

- `contracts.py`：请求、响应、错误分类与 `ImageGenerationProvider` Protocol。
- `gemini_native.py`：调用 Gemini `generateContent`，传递 `imageConfig.aspectRatio` 和
  `imageConfig.imageSize`，读取 `candidates[].content.parts[].inlineData`。
- `openai_images.py`：文生图调用 `/images/generations`，编辑调用 multipart `/images/edits`，供
  `openai-images` 和经过能力测试的 `openai-compatible-images` 使用；它把 Base64 或临时 URL
  统一转换为图片字节，并将系统白色编辑蒙版转换为 OpenAI 透明编辑区域。
- `openai_chat_image.py`：旧版兼容入口，调用 `/chat/completions`，读取 Markdown/data URL 或内容块中的图片。

协议差异由 `platform/image_generation/protocols.py` 的受控配置决定，不允许在模型配置中写任意
上游请求模板：

- `gemini-native`：管理员声明 `auth_mode`、可用画幅比例和像素档位；支持 `x-goog-api-key` 与 Bearer，
  通过 `inlineData` 发送主图、参考图和蒙版。
- `openai-images`：管理员声明预设尺寸；只有显式开启并配置宽高/像素约束后，才允许自定义尺寸。
- `openai-compatible-images`：仅允许管理员声明的预设尺寸，不能向不明兼容网关透传任意宽高。
- `openai-chat-image`：仅为旧模型保留，尺寸由模型决定，不作为新配置推荐项。

提供商实现不得把 API Key、原始提示词、图片 Base64 或第三方临时 URL 写入日志、追溯记录或 API 响应。
临时 URL 必须先经公网地址校验，再由服务端下载，后续交给 `media.generated_images` 校验和持久化。

`ImageGenerationRequest.notify_provider_dispatch()` 用于记录供应商调用审计时点：具体协议应在完成本地
请求构造、即将执行网络调用前调用它。积分只会在输出图片通过校验并成功落库后确认；任何失败路径
都会退回仍处于预扣状态的积分。新增协议适配器必须遵守这一约定。

新增厂商时实现 `ImageGenerationProvider`，并在 `platform.image_generation.service.build_image_generation_provider`
中显式注册，同时在协议配置层限定可配置字段与输出能力。聊天生图协议只复用 OpenAI 兼容传输格式，
不复用查题模型的配置或答题调用链路。
