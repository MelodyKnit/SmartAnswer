# 图片生成提供商适配

本包定义独立于查题聊天模型的文本生图契约，并提供两种 OpenAI 兼容协议实现。

- `contracts.py`：请求、响应、错误分类与 `ImageGenerationProvider` Protocol。
- `openai_images.py`：调用 `/images/generations`，把 Base64 或临时 URL 统一转换为图片字节。
- `openai_chat_image.py`：调用 `/chat/completions`，读取 Markdown/data URL 或内容块中的图片并转换为图片字节。

提供商实现不得把 API Key、原始提示词、图片 Base64 或第三方临时 URL 写入日志、追溯记录或 API 响应。临时 URL 必须先经公网地址校验，再由服务端下载，后续交给 `media.generated_images` 校验和持久化。

新增厂商时实现 `ImageGenerationProvider`，并在 `platform.image_generation.service.build_image_generation_provider` 中显式注册。聊天生图协议只复用 OpenAI 兼容传输格式，不复用查题模型的配置或答题调用链路。
