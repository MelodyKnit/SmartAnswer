"""大模型调用追溯的轻量收集层。

该模块用 contextvar 在一次查询的生命周期内串联 request_id，并提供一个可由运行时
注入的「落库回调」。提供者层（providers）只依赖此处的纯函数接口记录每次外部调用，
不直接依赖 platform/storage，避免循环依赖。

设计要点：
- request_id 通过 contextvar 在线程/协程内传播，由路由层在每次查询开始时设置。
- sink 是一个可选回调 `Callable[[dict], None]`，运行时把它指向平台仓储的写入方法。
- 任何记录失败都被吞掉，绝不影响主答题流程。
"""

from __future__ import annotations

import time
import uuid
from contextvars import ContextVar
from typing import Callable

# 当前查询的关联 ID（同一次 /query 内多次模型/检索调用共享）
_REQUEST_ID: ContextVar[str] = ContextVar("llm_trace_request_id", default="")

# 运行时注入的落库回调；为 None 时记录被静默丢弃。
_SINK: Callable[[dict], None] | None = None


def set_trace_sink(sink: Callable[[dict], None] | None) -> None:
    """注入（或清除）追溯落库回调。由运行时在组装服务时调用。"""
    global _SINK
    _SINK = sink


def new_request_id() -> str:
    """生成并设置一个新的查询关联 ID，返回该 ID。"""
    request_id = uuid.uuid4().hex
    _REQUEST_ID.set(request_id)
    return request_id


def set_request_id(request_id: str) -> None:
    """显式设置当前查询关联 ID。"""
    _REQUEST_ID.set(request_id or "")


def get_request_id() -> str:
    """读取当前查询关联 ID（未设置时为空串）。"""
    return _REQUEST_ID.get()


def reset_request_id() -> None:
    """清除当前查询关联 ID。"""
    _REQUEST_ID.set("")


def record_trace(
    *,
    phase: str,
    model_id: str = "",
    model_name: str = "",
    base_url: str = "",
    provider: str = "",
    question_title: str = "",
    prompt: str = "",
    evidence: list | None = None,
    response_text: str = "",
    candidate_answer: str | None = None,
    confidence: float = 0.0,
    ok: bool = True,
    error: str = "",
    elapsed_ms: float = 0.0,
) -> None:
    """记录一次外部调用追溯。无 sink 或异常时静默返回，绝不影响主流程。"""
    sink = _SINK
    if sink is None:
        return
    payload = {
        "trace_id": uuid.uuid4().hex,
        "request_id": _REQUEST_ID.get(),
        "phase": phase,
        "model_id": model_id,
        "model_name": model_name,
        "base_url": base_url,
        "provider": provider,
        "question_title": question_title,
        "prompt": prompt,
        "evidence": list(evidence or ()),
        "response_text": response_text,
        "candidate_answer": candidate_answer,
        "confidence": float(confidence or 0.0),
        "ok": bool(ok),
        "error": error,
        "elapsed_ms": float(elapsed_ms or 0.0),
        "created_at": time.time(),
    }
    try:
        sink(payload)
    except Exception:
        # 追溯落库失败不得影响答题主流程
        pass
