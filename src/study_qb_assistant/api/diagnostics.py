"""服务状态与运行日志诊断。"""

from __future__ import annotations

import json

from ..answering import AnswerService
from ..logger import log_path, recent_events
from ..platform.usage.time_ranges import local_day_range_from_text
from ..search import LocalQuestionIndex


def status_payload(lookup: LocalQuestionIndex | AnswerService) -> dict:
    """构造服务状态响应。"""
    status = lookup.status()
    return {
        "ok": True,
        "service": "study-question-bank-assistant",
        **status,
    }

def debug_events_payload(start_date: str = "", end_date: str = "") -> dict[str, object]:
    """返回最近一批结构化事件，支持根据日期区间过滤本地日志文件。"""
    limit = 2000
    start_date = start_date.strip()
    end_date = end_date.strip()

    if not start_date and not end_date:
        return {"ok": True, "events": recent_events()}

    path = log_path()
    if not path.exists():
        return {"ok": True, "events": []}

    if start_date and not end_date:
        end_date = start_date
    elif end_date and not start_date:
        start_date = end_date

    start_label, _start_time, _start_end = local_day_range_from_text(start_date)
    end_label, _end_start, _end_time = local_day_range_from_text(end_date)
    if start_label > end_label:
        raise ValueError("日期范围无效")

    events = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line_str = line.strip()
            if not line_str:
                continue
            try:
                event_dict = json.loads(line_str)
            except json.JSONDecodeError:
                continue
            ts = event_dict.get("ts")
            if not ts or len(str(ts)) < 10:
                continue
            event_date = str(ts)[:10]
            if start_label <= event_date <= end_label:
                events.append(event_dict)

    return {"ok": True, "events": events[-limit:]}
