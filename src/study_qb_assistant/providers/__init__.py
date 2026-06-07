"""模型及检索服务提供商适配模块。

该包定义了各种模型推理接口与外部搜索接口的抽象基类与具体实现类（如 OpenAI 兼容接口、搜索增强服务等）。
"""

from .base import ModelProvider
from .openai_compatible import OpenAICompatibleProvider
from .search_augmented import SearchAugmentedModelProvider
from .web_search import build_search_provider_from_env

__all__ = [
    "ModelProvider",
    "OpenAICompatibleProvider",
    "SearchAugmentedModelProvider",
    "build_search_provider_from_env",
]
