# 图片生成提供商适配

本包定义独立于查题聊天模型的文本生图契约，并提供三种正式调用协议与一个旧版兼容协议。

- `contracts.py`：请求、响应、错误分类与 `ImageGenerationProvider` Protocol。
- `gemini_native.py`：调用 Gemini `generateContent`，传递 `imageConfig.aspectRatio` 和
  `imageConfig.imageSize`，读取 `candidates[].content.parts[].inlineData`。
- `openai_images.py`：调用 `/images/generations`，供 `openai-images` 和经过连通性测试的
  `openai-compatible-images` 使用，把 Base64 或临时 URL 统一转换为图片字节。
- `openai_chat_image.py`：旧版兼容入口，调用 `/chat/completions`，读取 Markdown/data URL 或内容块中的图片。

协议差异由 `platform/image_generation/protocols.py` 的受控配置决定，不允许在模型配置中写任意
上游请求模板：

- `gemini-native`：管理员声明 `auth_mode`、可用画幅比例和像素档位；支持 `x-goog-api-key` 与 Bearer。
- `openai-images`：管理员声明预设尺寸；只有显式开启并配置宽高/像素约束后，才允许自定义尺寸。
- `openai-compatible-images`：仅允许管理员声明的预设尺寸，不能向不明兼容网关透传任意宽高。
- `openai-chat-image`：仅为旧模型保留，尺寸由模型决定，不作为新配置推荐项。

提供商实现不得把 API Key、原始提示词、图片 Base64 或第三方临时 URL 写入日志、追溯记录或 API 响应。临时 URL 必须先经公网地址校验，再由服务端下载，后续交给 `media.generated_images` 校验和持久化。

新增厂商时实现 `ImageGenerationProvider`，并在 `platform.image_generation.service.build_image_generation_provider`
中显式注册，同时在协议配置层限定可配置字段与输出能力。聊天生图协议只复用 OpenAI 兼容传输格式，
不复用查题模型的配置或答题调用链路。
