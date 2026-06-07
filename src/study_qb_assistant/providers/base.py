"""基于模型的答案生成服务提供商接口契约。

该模块使用 Protocol 声明了模型服务提供者的抽象接口，以保证各个具体模型服务类具有一致的方法签名。
"""

from __future__ import annotations

from typing import Protocol

from ..models import ModelAnswer, QuestionQuery


class ModelProvider(Protocol):
    """可插拔模型提供商的极简协议接口。

    任何具体的大语言模型生成服务（如 OpenAI 接口、本地 Ollama 服务或 Search-Augmented 等）都必须实现此协议。
    """

    # 提供商的唯一名称标识
    provider_name: str

    def answer(self, query: QuestionQuery) -> ModelAnswer:
        """为给定的题目查询生成结构化的候选答案及解析。

        参数:
            query: 题目查询结构体 (QuestionQuery)。

        返回:
            ModelAnswer: 包含模型生成答案、解析以及状态元数据的模型答案结构体。
        """
