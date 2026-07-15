"""平台统计使用的上海时区自然日工具。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ...logger import log_path

LOCAL_TIMEZONE = ZoneInfo("Asia/Shanghai")


def local_day_range_from_text(date_text: str = "") -> tuple[str, float, float]:
    """把日期文本转换为上海时区自然日范围。"""

    if date_text.strip():
        target = datetime.strptime(date_text.strip(), "%Y-%m-%d").replace(
            tzinfo=LOCAL_TIMEZONE
        )
    else:
        now = datetime.now(LOCAL_TIMEZONE)
        target = datetime(now.year, now.month, now.day, tzinfo=LOCAL_TIMEZONE)
    start = datetime(target.year, target.month, target.day, tzinfo=LOCAL_TIMEZONE)
    end = start + timedelta(days=1)
    return start.strftime("%Y-%m-%d"), start.timestamp(), end.timestamp()


def local_day_window_from_dates(
    start_date: str = "",
    end_date: str = "",
) -> tuple[float | None, float | None]:
    """把日期区间转换为上海时区自然日闭开区间。"""

    normalized_start = start_date.strip()
    normalized_end = end_date.strip()
    start_time: float | None = None
    end_time: float | None = None
    start_label = ""
    end_label = ""
    if normalized_start:
        start_label, start_time, _ = local_day_range_from_text(normalized_start)
    if normalized_end:
        end_label, _, end_time = local_day_range_from_text(normalized_end)
    if start_time is not None and end_time is not None and start_label > end_label:
        raise ValueError("start_date must be on or before end_date")
    return start_time, end_time


def current_local_day_range() -> tuple[float, float]:
    """返回当前上海自然日的时间戳范围。"""

    _, start_time, end_time = local_day_range_from_text("")
    return start_time, end_time


def recent_day_range(days: int) -> tuple[float, float]:
    """返回最近 N 个自然日的范围，包含今天。"""

    normalized_days = max(1, min(int(days), 365))
    today_label, _, today_end = local_day_range_from_text("")
    start_day = (
        datetime.strptime(today_label, "%Y-%m-%d").replace(tzinfo=LOCAL_TIMEZONE)
        - timedelta(days=normalized_days - 1)
    )
    return start_day.timestamp(), today_end


def day_windows(days: int) -> list[tuple[str, float, float]]:
    """返回最近 N 个自然日的标签和边界。"""

    normalized_days = max(1, min(int(days), 365))
    start_time, _ = recent_day_range(normalized_days)
    start_day = datetime.fromtimestamp(start_time, LOCAL_TIMEZONE)
    windows: list[tuple[str, float, float]] = []
    for offset in range(normalized_days):
        day_start = start_day + timedelta(days=offset)
        day_end = day_start + timedelta(days=1)
        windows.append(
            (day_start.strftime("%Y-%m-%d"), day_start.timestamp(), day_end.timestamp())
        )
    return windows


def count_query_events_for_date(date_label: str) -> tuple[int, int]:
    """统计运行日志中指定自然日的 query 事件数量。"""

    path = log_path()
    if not path.exists():
        return 0, 0
    query_count = 0
    malformed_lines = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                malformed_lines += 1
                if f'"ts": "{date_label}' in line and '"event": "query"' in line:
                    query_count += 1
                continue
            if local_date_from_log_timestamp(str(payload.get("ts") or "")) != date_label:
                continue
            if str(payload.get("event") or "") == "query":
                query_count += 1
    return query_count, malformed_lines


def local_date_from_log_timestamp(value: str) -> str:
    """把运行日志时间戳转换成上海自然日标签。"""

    timestamp = value.strip()
    if not timestamp:
        return ""
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return timestamp[:10]
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=LOCAL_TIMEZONE)
    return parsed.astimezone(LOCAL_TIMEZONE).strftime("%Y-%m-%d")
