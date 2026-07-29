"""生图提供商的稳定内部契约。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ImageInputAsset:
    """执行期加载的私有输入图片；字节不进入任务持久化记录。"""

    content: bytes
    mime_type: str = "image/png"
    role: str = "reference"


@dataclass(frozen=True, slots=True)
class ImageGenerationRequest:
    """一次文本生图、整图编辑、局部编辑或多参考图编辑请求。"""

    prompt: str
    size: str
    request_id: str
    mode: str = "text_to_image"
    input_images: tuple[ImageInputAsset, ...] = ()
    mask_image: ImageInputAsset | None = None
    output_options: dict[str, str] = field(default_factory=dict)
    on_provider_dispatch: Callable[[], None] | None = None

    def notify_provider_dispatch(self) -> None:
        """通知任务编排器请求即将发往上游，仅记录调用审计时点。"""

        if self.on_provider_dispatch is not None:
            self.on_provider_dispatch()


@dataclass(frozen=True, slots=True)
class GeneratedImage:
    """已规范化的供应商图片结果。"""

    content: bytes
    mime_type: str
    width: int
    height: int
    provider_request_id: str = ""
    revised_prompt: str = ""


@runtime_checkable
class ImageGenerationProvider(Protocol):
    """文本生图提供商端口。"""

    provider_name: str

    def generate(self, request: ImageGenerationRequest) -> GeneratedImage:
        """生成并返回已下载、可校验的图片字节。"""


class ImageGenerationProviderError(RuntimeError):
    """供应商调用失败，附带可安全暴露的错误分类。"""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
